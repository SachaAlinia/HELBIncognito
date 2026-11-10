from django import forms

from .models import Game


class GameForm(forms.ModelForm):
    """Form used to create a new game with its settings."""

    class Meta:
        model = Game
        fields = [
            "name",
            "short_description",
            "total_rounds",
            "round_duration_seconds",
            "message_cooldown_seconds",
            "max_message_length",
            "min_players",
        ]