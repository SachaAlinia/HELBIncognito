"""Bounded worker passes; database locks are never held during model inference."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from game import services as game_services
from game.models import Game, GamePlayer, Message
from .providers import AgentProviderError, generate_decision
from .services import play_incognito


def _config(player):
    return (player.ai_enabled, player.ai_agent_type, player.ai_model_name,
            player.ai_prompt, player.ai_config_revision)


def eligible_players(now=None):
    now = now or timezone.now()
    return GamePlayer.objects.filter(ai_enabled=True, user__is_active=True, game__status=Game.Status.IN_PROGRESS).filter(
        Q(ai_next_run_at__isnull=True) | Q(ai_next_run_at__lte=now)
    ).filter(Q(ai_lease_until__isnull=True) | Q(ai_lease_until__lte=now)).order_by("ai_next_run_at", "pk")


@transaction.atomic
def _claim(player_id):
    # Lock order is the same as all human actions and config updates.
    game_id = GamePlayer.objects.filter(pk=player_id).values_list("game_id", flat=True).first()
    if game_id is None:
        return None
    try:
        game = game_services._lock_game(game_id)
    except Game.DoesNotExist:
        return None
    now = timezone.now()
    if not eligible_players(now).filter(pk=player_id).exists():
        return None
    round_ = game_services._advance(game, now)
    if round_ is None:
        return None
    player = GamePlayer.objects.select_related("user").get(pk=player_id)
    last = Message.objects.filter(author=player).order_by("-sent_at").first()
    if last and now < last.sent_at + timedelta(seconds=game.message_cooldown_seconds):
        player.ai_next_run_at = last.sent_at + timedelta(seconds=game.message_cooldown_seconds)
        player.save(update_fields=["ai_next_run_at"])
        return None
    token = secrets.token_hex(16)
    player.ai_lease_token = token
    player.ai_lease_until = now + timedelta(seconds=settings.AGENTS_LEASE_SECONDS)
    player.save(update_fields=["ai_lease_token", "ai_lease_until"])
    aliases = list(round_.aliases.order_by("pk").values("player_id", "alias"))
    names = {alias["player_id"]: alias["alias"] for alias in aliases}
    messages = list(round_.messages.order_by("-sent_at").values("author_id", "content")[:12])
    context = {
        "game": "incognito", "round": round_.number,
        "rules": "Chat anonymously. Vote for another player to award them a point. A unique vote leader wins the round.",
        "your_alias": names.get(player.pk, ""),
        "players": aliases[:50],
        "allowed_target_ids": [row["player_id"] for row in aliases if row["player_id"] != player.pk][:50],
        "max_message_length": min(game.max_message_length, 2000),
        "messages": [{"alias": names.get(row["author_id"], ""), "message": row["content"][:400]}
                     for row in reversed(messages)],
    }
    return player, round_.pk, token, _config(player), context


@transaction.atomic
def _finish(claim, decision=None, error=""):
    original, round_id, token, config, _ = claim
    try:
        game = game_services._lock_game(original.game_id)
    except Game.DoesNotExist:
        return False
    player = GamePlayer.objects.filter(pk=original.pk, ai_lease_token=token).select_related("user").first()
    if player is None:
        return False  # A newer lease fenced this worker out.
    now = timezone.now()
    current = game_services._advance(game, now)
    unchanged = _config(player) == config and player.user.is_active
    applied = False
    if unchanged and current and current.pk == round_id:
        if not error:
            try:
                # Savepoint ensures a rejected action cannot leave a partial vote.
                with transaction.atomic():
                    play_incognito(player, round_id, decision)
                applied = True
            except ValidationError:
                error = "The game state changed; the agent will try again later."
        player.ai_failure_count = min(player.ai_failure_count + 1, 10) if error else 0
        player.ai_last_error = error
        player.ai_last_run_at = now
        delay = min(300, 15 * 2 ** (player.ai_failure_count - 1)) if error else settings.AGENTS_INTERVAL_SECONDS
        player.ai_next_run_at = now + timedelta(seconds=max(delay, game.message_cooldown_seconds))
        player.save(update_fields=["ai_failure_count", "ai_last_error", "ai_last_run_at", "ai_next_run_at"])
    player.ai_lease_token = ""
    player.ai_lease_until = None
    player.save(update_fields=["ai_lease_token", "ai_lease_until"])
    return applied


def run_incognito_agents(limit=10, dry_run=False):
    ids = list(eligible_players().values_list("pk", flat=True)[:limit])
    if dry_run:
        return len(ids)  # Read-only: no lease, model call, or action.
    completed = 0
    for player_id in ids:
        claim = _claim(player_id)
        if claim is None:
            continue
        player, _, _, _, context = claim
        try:
            decision = generate_decision(player.ai_agent_type, player.ai_model_name, player.ai_prompt, context)
        except AgentProviderError as exc:
            _finish(claim, error=str(exc))
        except Exception:
            _finish(claim, error="The agent failed; check server setup.")
        else:
            completed += int(_finish(claim, decision=decision))
    return completed
