"""Game rules shared by HTTP views and agents. Assisted by OpenAI Codex."""
import secrets
import string
from collections import Counter
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import ALIAS_LENGTH, Game, GamePlayer, Message, Round, RoundAlias, Vote


def _lock_game(game_id):
    # Acquire a write lock before reading: select_for_update alone does not lock SQLite.
    Game.objects.filter(pk=game_id).update(status=F("status"))
    return Game.objects.select_for_update().get(pk=game_id)


def _alias(round_, player):
    existing = RoundAlias.objects.filter(round=round_, player=player).first()
    if existing:
        return existing
    alphabet = string.ascii_letters + string.digits
    while True:
        name = "".join(secrets.choice(alphabet) for _ in range(ALIAS_LENGTH))
        if not round_.aliases.filter(alias=name).exists():
            return RoundAlias.objects.create(round=round_, player=player, alias=name)


def _start_round(game, number, now):
    round_ = Round.objects.create(game=game, number=number, started_at=now)
    for player in game.game_players.all():
        _alias(round_, player)
    return round_


def _advance(game, now):
    if game.status == Game.Status.WAITING:
        if game.game_players.count() < game.min_players:
            return None
        game.status = Game.Status.IN_PROGRESS
        game.save(update_fields=["status"])
        return _start_round(game, 1, now)
    if game.status == Game.Status.FINISHED:
        return None
    round_ = game.rounds.filter(ended_at__isnull=True).first()
    if round_ is None:
        raise ValidationError("This game has no active round.")
    deadline = round_.started_at + timedelta(seconds=game.round_duration_seconds)
    if now < deadline:
        return round_
    # Only voters who sent a message count. A tie (or no votes) awards no point.
    active_voters = round_.messages.values("author_id")
    counts = Counter(round_.votes.filter(voter_id__in=active_voters).values_list("target_id", flat=True))
    leaders = [pk for pk, count in counts.items() if count == max(counts.values())]
    if len(leaders) == 1:
        round_.winner_id = leaders[0]
        GamePlayer.objects.filter(pk=leaders[0]).update(total_score=F("total_score") + 1)
    round_.ended_at = deadline
    round_.save(update_fields=["winner", "ended_at"])
    if round_.number == game.total_rounds:
        game.status = Game.Status.FINISHED
        game.finished_at = deadline
        game.save(update_fields=["status", "finished_at"])
        return None
    # A new round gets its full duration even after a period without requests.
    return _start_round(game, round_.number + 1, now)


@transaction.atomic
def advance_game(game_id, now=None):
    return _advance(_lock_game(game_id), now or timezone.now())


@transaction.atomic
def join_game(game_id, user):
    game = _lock_game(game_id)
    if game.status == Game.Status.FINISHED:
        raise ValidationError("This game has finished.")
    # Close an expired final round before accepting a late join.
    if game.status == Game.Status.IN_PROGRESS:
        _advance(game, timezone.now())
        if game.status == Game.Status.FINISHED:
            raise ValidationError("This game has finished.")
    player, _ = GamePlayer.objects.get_or_create(game=game, user=user)
    round_ = _advance(game, timezone.now())
    if round_:
        _alias(round_, player)
    return player


def _active_player(game, user, now, round_id):
    round_ = _advance(game, now)
    if not round_ or round_.pk != round_id:
        raise ValidationError("This round is no longer active. Refresh the game.")
    try:
        player = game.game_players.get(user=user)
    except GamePlayer.DoesNotExist:
        raise ValidationError("Join the game first.")
    return round_, player


@transaction.atomic
def send_message(game_id, user, round_id, content):
    game = _lock_game(game_id)
    now = timezone.now()
    round_, player = _active_player(game, user, now, round_id)
    if not content.strip() or len(content) > game.max_message_length:
        raise ValidationError("The message is empty or exceeds the character limit.")
    last = Message.objects.filter(author=player).order_by("-sent_at").first()
    if last and now < last.sent_at + timedelta(seconds=game.message_cooldown_seconds):
        raise ValidationError("Please wait before sending another message.")
    return Message.objects.create(round=round_, author=player, content=content)


@transaction.atomic
def cast_vote(game_id, user, round_id, target_id):
    game = _lock_game(game_id)
    round_, player = _active_player(game, user, timezone.now(), round_id)
    if target_id == player.pk or not round_.aliases.filter(player_id=target_id).exists():
        raise ValidationError("Choose another player in this round.")
    if not round_.messages.filter(author=player).exists():
        raise ValidationError("Send a message before voting.")
    return Vote.objects.update_or_create(round=round_, voter=player, defaults={"target_id": target_id})[0]
