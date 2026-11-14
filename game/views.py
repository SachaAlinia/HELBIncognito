from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db import transaction
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import GameForm
from .models import Game, GamePlayer
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
    is_player = game.game_players.filter(user=request.user).exists()
    players = list(game.game_players.select_related("user").order_by("-total_score", "joined_at"))
    leaders = [player for player in players if players and player.total_score == players[0].total_score]
    return render(
        request,
        "game/game_detail.html",
        {"game": game, "players": players, "winner": leaders[0] if len(leaders) == 1 else None,
         "is_player": is_player, "round": round_,
         "aliases": round_.aliases.exclude(player__user=request.user) if round_ else [],
         "chat": _chat(round_) if round_ else [],
         "history": game.rounds.filter(ended_at__isnull=False).select_related("winner__user").prefetch_related("aliases", "messages")},
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
            services.send_message(game_id, request.user, round_id, request.POST.get("content", ""))
    except (ValidationError, ValueError) as error:
        messages.error(request, error.messages[0] if isinstance(error, ValidationError) else "Invalid selection.")
    return redirect("game-detail", game_id=game_id)


@login_required
def state(request, game_id):
    game = get_object_or_404(Game, pk=game_id)
    round_ = services.advance_game(game.pk)
    game.refresh_from_db()
    response = JsonResponse({"round_id": round_.pk if round_ else None,
                             "player_count": game.game_players.count(),
                             "status": game.status, "messages": _chat(round_) if round_ else []})
    response["Cache-Control"] = "no-store"
    return response
