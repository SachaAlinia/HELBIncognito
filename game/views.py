from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from .forms import GameForm
from .models import Game, GamePlayer


def home(request):
    """List joinable public games, most active (most players) first."""
    games = (
        Game.objects.filter(status__in=[Game.Status.WAITING, Game.Status.IN_PROGRESS])
        .annotate(player_count=Count("game_players"))
        .order_by("-player_count", "-created_at")
    )
    return render(request, "game/home.html", {"games": games})


@login_required
def create_game(request):
    """Create a game; the creator automatically joins it."""
    form = GameForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        game = form.save(commit=False)
        game.creator = request.user
        game.save()
        GamePlayer.objects.create(game=game, user=request.user)
        return redirect("game-detail", game_id=game.id)
    return render(request, "game/create_game.html", {"form": form})


@login_required
def game_detail(request, game_id):
    """Game page: shows info and players, and lets the user join."""
    game = get_object_or_404(Game, id=game_id)
    is_player = game.game_players.filter(user=request.user).exists()
    return render(
        request,
        "game/game_detail.html",
        {"game": game, "players": game.game_players.select_related("user"), "is_player": is_player},
    )


@login_required
def join_game(request, game_id):
    """Add the current user to the game (POST only, no duplicates)."""
    game = get_object_or_404(Game, id=game_id)
    if request.method == "POST" and game.status != Game.Status.FINISHED:
        GamePlayer.objects.get_or_create(game=game, user=request.user)
    return redirect("game-detail", game_id=game.id)