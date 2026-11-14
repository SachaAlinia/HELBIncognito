"""Truthful public statistics regressions. Assisted by OpenAI Codex."""
from datetime import datetime, timezone

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from game.models import Game, GamePlayer


class PublicProfileTests(TestCase):
    def setUp(self):
        self.alice = get_user_model().objects.create_user("alice", email="private@example.com")
        self.bob = get_user_model().objects.create_user("bob")
        self.joined = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        self.finished = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)

    def participation(self, name, status, alice_score, bob_score):
        game = Game.objects.create(name=name, creator=self.alice, status=status,
                                   finished_at=self.finished if status == Game.Status.FINISHED else None)
        alice = GamePlayer.objects.create(game=game, user=self.alice, total_score=alice_score)
        GamePlayer.objects.create(game=game, user=self.bob, total_score=bob_score)
        GamePlayer.objects.filter(pk=alice.pk).update(joined_at=self.joined)
        return game

    def test_counts_join_dates_unique_final_wins_and_empty_days(self):
        self.participation("Win", Game.Status.FINISHED, 2, 1)
        self.participation("Tie", Game.Status.FINISHED, 1, 1)
        self.participation("Loss", Game.Status.FINISHED, 0, 1)
        self.participation("Still playing", Game.Status.IN_PROGRESS, 4, 0)
        self.participation("Waiting", Game.Status.WAITING, 0, 0)
        # Creating a game without joining it does not count as participation.
        Game.objects.create(name="Created only", creator=self.alice)
        response = self.client.get(reverse("public-profile", args=[self.alice.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["games_played"], 5)
        self.assertEqual(response.context["games_won"], 1)
        self.assertEqual([(row["played"], row["won"]) for row in response.context["daily_stats"]], [(5, 0), (0, 0), (0, 1)])
        self.assertNotContains(response, "private@example.com")
        self.assertContains(response, "daily-chart")

    def test_no_history_and_unknown_player(self):
        self.assertContains(self.client.get(reverse("public-profile", args=[self.alice.pk])), "No games played yet")
        self.assertEqual(self.client.get(reverse("public-profile", args=[99999])).status_code, 404)
