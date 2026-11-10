from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

# Default game settings (named constants instead of magic numbers)
DEFAULT_TOTAL_ROUNDS = 3
DEFAULT_ROUND_DURATION_SECONDS = 120
DEFAULT_MESSAGE_COOLDOWN_SECONDS = 5
DEFAULT_MAX_MESSAGE_LENGTH = 180
DEFAULT_MIN_PLAYERS = 2
ALIAS_LENGTH = 5  # the "n" characters of the random pseudonym


class Game(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting for players"
        IN_PROGRESS = "in_progress", "In progress"
        FINISHED = "finished", "Finished"

    name = models.CharField(max_length=100)
    short_description = models.CharField(max_length=200)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_games"
    )
    total_rounds = models.PositiveSmallIntegerField(
        default=DEFAULT_TOTAL_ROUNDS, validators=[MinValueValidator(1)]
    )
    round_duration_seconds = models.PositiveIntegerField(
        default=DEFAULT_ROUND_DURATION_SECONDS, validators=[MinValueValidator(10)]
    )
    message_cooldown_seconds = models.PositiveIntegerField(
        default=DEFAULT_MESSAGE_COOLDOWN_SECONDS
    )
    max_message_length = models.PositiveIntegerField(
        default=DEFAULT_MAX_MESSAGE_LENGTH, validators=[MinValueValidator(1)]
    )
    min_players = models.PositiveSmallIntegerField(
        default=DEFAULT_MIN_PLAYERS, validators=[MinValueValidator(1)]
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.WAITING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    players = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="GamePlayer", related_name="games"
    )

    def __str__(self):
        return self.name


class GamePlayer(models.Model):
    """A user taking part in a game, with their score and AI agent settings."""

    class AgentType(models.TextChoices):
        LOCAL = "local", "Local model"
        API = "api", "API model"

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="game_players")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    total_score = models.PositiveIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    # AI agent settings
    ai_enabled = models.BooleanField(default=False)
    ai_prompt = models.TextField(blank=True)
    ai_agent_type = models.CharField(
        max_length=10, choices=AgentType.choices, default=AgentType.LOCAL
    )
    ai_model_name = models.CharField(max_length=50, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["game", "user"], name="unique_player_per_game")
        ]

    def __str__(self):
        return f"{self.user} in {self.game}"


class Round(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="rounds")
    number = models.PositiveSmallIntegerField()
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    # Null when nobody wins (tie or no votes)
    winner = models.ForeignKey(
        GamePlayer, null=True, blank=True, on_delete=models.SET_NULL, related_name="won_rounds"
    )

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["game", "number"], name="unique_round_number")
        ]

    def __str__(self):
        return f"{self.game} - round {self.number}"


class RoundAlias(models.Model):
    """Random pseudonym of a player, regenerated for every round."""

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="aliases")
    player = models.ForeignKey(GamePlayer, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=ALIAS_LENGTH)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["round", "player"], name="unique_alias_per_player"),
            models.UniqueConstraint(fields=["round", "alias"], name="unique_alias_per_round"),
        ]

    def __str__(self):
        return self.alias


class Message(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(GamePlayer, on_delete=models.CASCADE, related_name="messages")
    content = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sent_at"]


class Vote(models.Model):
    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name="votes")
    voter = models.ForeignKey(GamePlayer, on_delete=models.CASCADE, related_name="votes_cast")
    target = models.ForeignKey(GamePlayer, on_delete=models.CASCADE, related_name="votes_received")

    class Meta:
        constraints = [
            # One vote per voter per round: changing a vote updates this row
            models.UniqueConstraint(fields=["round", "voter"], name="one_vote_per_round"),
            models.CheckConstraint(
                check=~models.Q(voter=models.F("target")), name="no_self_vote"
            ),
        ]


class Script(models.Model):
    """Reusable pre-prompt for AI agents."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="scripts"
    )
    title = models.CharField(max_length=100)
    content = models.TextField()

    def __str__(self):
        return self.title