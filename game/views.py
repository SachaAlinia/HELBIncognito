from django.contrib.auth.decorators import login_required
from datetime import timedelta

from django.db.models import Count, F
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AgentConfigForm, GameForm, ScriptForm
from .models import Game, GamePlayer, Script
from . import services


def home(request):
    """List joinable public games, most active (most players) first."""
    games = (
        Game.objects.filter(status__in=[Game.Status.WAITING, Game.Status.IN_PROGRESS])
        .annotate(player_count=Count("game_players"))
        .order_by("-player_count", "-created_at")
    )
    return render(request, "game/home.html", {"games": games, "finished_games": Game.objects.filter(status=Game.Status.FINISHED).order_by("-finished_at")})


@login_required
@transaction.atomic
def create_game(request):
    """Create a game; the creator automatically joins it."""
    form = GameForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        game = form.save(commit=False)
        game.creator = request.user
        game.save()
        services.join_game(game.pk, request.user)
        return redirect("game-detail", game_id=game.id)
    return render(request, "game/create_game.html", {"form": form})


@login_required
def game_detail(request, game_id):
    """Game page: shows info and players, and lets the user join."""
    game = get_object_or_404(Game, id=game_id)
    round_ = services.advance_game(game.pk)
    game.refresh_from_db()
    players = list(game.game_players.select_related("user").order_by("-total_score", "joined_at"))
    own_player = next((player for player in players if player.user_id == request.user.pk), None)
    leaders = [player for player in players if players and player.total_score == players[0].total_score]
    # Assisted by OpenAI Codex: retain explicit participation, including zero scores.
    history = []
    for past in game.rounds.filter(ended_at__isnull=False).select_related("winner__user").prefetch_related("aliases", "messages"):
        participants = {alias.player_id for alias in past.aliases.all()}
        history.append({"round": past, "chat": _chat(past), "scores": [
            {"player": player, "participated": player.pk in participants,
             "points": int(player.pk == past.winner_id)} for player in players
        ]})
    own_alias = round_.aliases.filter(player=own_player).first() if round_ and own_player else None
    own_vote = round_.votes.filter(voter=own_player).first() if round_ and own_player else None
    aliases = list(round_.aliases.exclude(player__user=request.user)) if round_ else []
    vote_alias = next((alias.alias for alias in aliases if own_vote and alias.player_id == own_vote.target_id), None)
    agent_form = AgentConfigForm(instance=own_player, user=request.user) if own_player else None
    return render(
        request,
        "game/game_detail.html",
        {"game": game, "players": players, "winner": leaders[0] if len(leaders) == 1 else None,
         "is_player": own_player is not None, "round": round_, "own_player": own_player,
         "own_alias": own_alias, "own_vote": own_vote, "vote_alias": vote_alias,
         "agent_form": agent_form, "aliases": aliases,
         "round_deadline": round_.started_at + timedelta(seconds=game.round_duration_seconds) if round_ else None,
         "chat": _chat(round_) if round_ else [],
         "history": history},
    )


@login_required
@require_POST
def join_game(request, game_id):
    """Add the current user to the game (POST only, no duplicates)."""
    game = get_object_or_404(Game, id=game_id)
    try:
        services.join_game(game.pk, request.user)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    return redirect("game-detail", game_id=game.id)


def _chat(round_):
    aliases = dict(round_.aliases.values_list("player_id", "alias"))
    return [{"alias": aliases.get(message.author_id, "Anonymous"), "content": message.content}
            for message in round_.messages.all()]


@login_required
@require_POST
def action(request, game_id):
    get_object_or_404(Game, pk=game_id)
    try:
        round_id = int(request.POST.get("round_id", ""))
        if request.POST.get("action") == "vote":
            services.cast_vote(game_id, request.user, round_id, int(request.POST.get("target", "")))
        else:
            target = request.POST.get("target", "")
            services.send_message(game_id, request.user, round_id, request.POST.get("content", ""),
                                  target_id=int(target) if target else None)
    except (ValidationError, ValueError) as error:
        messages.error(request, error.messages[0] if isinstance(error, ValidationError) else "Invalid selection.")
    return redirect("game-detail", game_id=game_id)


@login_required
def state(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    round_ = services.advance_game(game.pk)
    game.refresh_from_db()
    player = game.game_players.filter(user=request.user).first()
    own_vote = round_.votes.filter(voter=player).first() if round_ and player else None
    vote_alias = round_.aliases.filter(player_id=own_vote.target_id).first() if own_vote else None
    response = JsonResponse({"round_id": round_.pk if round_ else None,
                             "player_count": game.game_players.count(),
                             "status": game.status, "messages": _chat(round_) if round_ else [],
                             "own_vote_alias": vote_alias.alias if vote_alias else None,
                             "own_agent": {"enabled": player.ai_enabled, "error": player.ai_last_error,
                                           "last_run_at": player.ai_last_run_at} if player else None})
    response["Cache-Control"] = "no-store"
    return response


# Assisted by OpenAI Codex: agents can only be configured by their own player.
@login_required
@require_POST
@transaction.atomic
def configure_agent(request, game_id):
    get_object_or_404(Game, pk=game_id)
    Game.objects.filter(pk=game_id).update(status=F("status"))
    game = Game.objects.select_for_update().get(pk=game_id)
    player = get_object_or_404(GamePlayer.objects.select_for_update(), game=game, user=request.user)
    if request.POST.get("action") == "stop":
        player.ai_enabled = False
        _reset_agent_schedule(player)
        player.save(update_fields=["ai_enabled", "ai_config_revision", "ai_last_error", "ai_next_run_at", "ai_failure_count"])
        messages.success(request, "Agent stopped.")
        return redirect("game-detail", game_id=game_id)
    form = AgentConfigForm(request.POST, instance=player, user=request.user)
    if game.status == Game.Status.FINISHED:
        messages.error(request, "This game has finished.")
    elif form.is_valid():
        player = form.save(commit=False)
        _reset_agent_schedule(player)
        player.save()
        messages.success(request, "Agent settings saved. The worker will use these settings on its next turn.")
    else:
        for field, errors in form.errors.items():
            label = form.fields[field].label if field in form.fields else "Agent"
            for error in errors:
                messages.error(request, f"{label}: {error}")
    return redirect("game-detail", game_id=game_id)


def _reset_agent_schedule(player):
    """Invalidate in-flight settings without releasing a worker's active lease."""
    player.ai_config_revision += 1
    player.ai_last_error = ""
    player.ai_next_run_at = None
    player.ai_failure_count = 0


@login_required
def script_list(request):
    return render(request, "game/script_list.html", {"scripts": request.user.scripts.order_by("title", "pk")})


@login_required
def script_edit(request, script_id=None):
    script = get_object_or_404(Script, pk=script_id, owner=request.user) if script_id else None
    form = ScriptForm(request.POST or None, instance=script)
    if request.method == "POST" and form.is_valid():
        script = form.save(commit=False)
        script.owner = request.user
        script.save()
        messages.success(request, "Script saved.")
        return redirect("script-list")
    return render(request, "game/script_form.html", {"form": form, "script": script})


@login_required
@require_POST
def script_delete(request, script_id):
    get_object_or_404(Script, pk=script_id, owner=request.user).delete()
    messages.success(request, "Script deleted. Existing agent prompt copies are unchanged.")
    return redirect("script-list")
