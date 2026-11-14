from collections import defaultdict
from datetime import timedelta

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.utils import timezone
from game.models import Game, GamePlayer
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm
from .models import Profile
from .services import update_profile


def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Your account has been created! You are now able to log in')
            return redirect('login')
    else:
        form = UserRegisterForm()
    return render(request, 'users/register.html', {'form': form})


@login_required
def profile(request):
    Profile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST,
                                   request.FILES,
                                   instance=request.user.profile)
        if u_form.is_valid() and p_form.is_valid():
            update_profile(u_form, p_form)
            messages.success(request, f'Your account has been updated!')
            return redirect('profile')

    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)

    context = {
        'u_form': u_form,
        'p_form': p_form
    }

    return render(request, 'users/profile.html', context)


# Assisted by OpenAI Codex: public daily participation and unique final winners.
def public_profile(request, user_id):
    player_user = get_object_or_404(get_user_model(), pk=user_id)
    daily = defaultdict(lambda: {"played": 0, "won": 0})
    participations = GamePlayer.objects.filter(user=player_user).select_related("game").prefetch_related("game__game_players")
    wins = 0
    for participation in participations:
        joined_day = timezone.localtime(participation.joined_at).date()
        daily[joined_day]["played"] += 1
        game = participation.game
        if game.status != Game.Status.FINISHED or not game.finished_at:
            continue
        contestants = list(game.game_players.all())
        best_score = max((player.total_score for player in contestants), default=0)
        leaders = [player for player in contestants if player.total_score == best_score]
        if len(leaders) == 1 and leaders[0].pk == participation.pk:
            daily[timezone.localtime(game.finished_at).date()]["won"] += 1
            wins += 1
    # Zero days stay visible; played and wins have independent, explicit dates.
    rows = []
    if daily:
        day, end = min(daily), max(daily)
        maximum = max(max(counts.values()) for counts in daily.values()) or 1
        while day <= end:
            counts = daily.get(day, {"played": 0, "won": 0})
            rows.append({"date": day, **counts,
                         "played_height": counts["played"] * 120 / maximum,
                         "won_height": counts["won"] * 120 / maximum})
            day += timedelta(days=1)
    return render(request, "users/public_profile.html", {
        "player_user": player_user, "daily_stats": rows,
        "games_played": sum(row["played"] for row in rows), "games_won": wins,
    })
