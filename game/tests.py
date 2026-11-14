"""Game behavior tests. Assisted by OpenAI Codex."""
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from .models import Game, GamePlayer, Message, Vote
from . import services

class GameRulesTests(TestCase):
    def setUp(self):
        self.alice = get_user_model().objects.create_user("alice")
        self.bob = get_user_model().objects.create_user("bob")
        self.game = Game.objects.create(name="Test", creator=self.alice, total_rounds=1)
        self.a = services.join_game(self.game.pk, self.alice)
        self.assertFalse(self.game.rounds.exists())
        self.b = services.join_game(self.game.pk, self.bob)
        self.round = self.game.rounds.get()

    def close(self):
        return services.advance_game(self.game.pk, self.round.started_at + timedelta(seconds=121))

    def test_duplicate_join_and_aliases(self):
        services.join_game(self.game.pk, self.alice)
        self.assertEqual(self.game.game_players.count(), 2)
        self.assertEqual(len(set(self.round.aliases.values_list("alias", flat=True))), 2)

    def test_late_join_gets_alias(self):
        user = get_user_model().objects.create_user("late")
        player = services.join_game(self.game.pk, user)
        self.assertTrue(self.round.aliases.filter(player=player).exists())

    def test_cooldown_and_length(self):
        services.send_message(self.game.pk, self.alice, self.round.pk, "Hello")
        for user, content in [(self.alice, "Again"), (self.bob, "a"*181), (self.bob, " ")]:
            with self.assertRaises(ValidationError):
                services.send_message(self.game.pk, user, self.round.pk, content)

    def test_vote_rules_and_update(self):
        with self.assertRaises(ValidationError):
            services.cast_vote(self.game.pk, self.alice, self.round.pk, self.b.pk)
        services.send_message(self.game.pk, self.alice, self.round.pk, "Hello")
        with self.assertRaises(ValidationError):
            services.cast_vote(self.game.pk, self.alice, self.round.pk, self.a.pk)
        player = services.join_game(self.game.pk, get_user_model().objects.create_user("third"))
        services.cast_vote(self.game.pk, self.alice, self.round.pk, self.b.pk)
        services.cast_vote(self.game.pk, self.alice, self.round.pk, player.pk)
        self.assertEqual(self.round.votes.count(), 1)
        self.assertEqual(self.round.votes.get().target_id, player.pk)

    def test_winner_awarded_once(self):
        services.send_message(self.game.pk, self.alice, self.round.pk, "Hello")
        services.cast_vote(self.game.pk, self.alice, self.round.pk, self.b.pk)
        self.close()
        self.close()
        self.b.refresh_from_db()
        self.assertEqual(self.b.total_score, 1)

    def test_tie(self):
        for user, target in [(self.alice, self.b), (self.bob, self.a)]:
            services.send_message(self.game.pk, user, self.round.pk, "Hello")
            services.cast_vote(self.game.pk, user, self.round.pk, target.pk)
        self.close()
        self.round.refresh_from_db()
        self.assertIsNone(self.round.winner)
        self.assertFalse(self.game.game_players.exclude(total_score=0).exists())

    def test_abstention(self):
        Vote.objects.create(round=self.round, voter=self.a, target=self.b)
        self.close()
        self.round.refresh_from_db()
        self.assertIsNone(self.round.winner)

    def test_expired_round(self):
        with patch("game.services.timezone.now", return_value=self.round.started_at + timedelta(seconds=121)):
            with self.assertRaises(ValidationError):
                services.send_message(self.game.pk, self.alice, self.round.pk, "Too late")
        self.assertFalse(Message.objects.exists())

    def test_foreign_target(self):
        other = Game.objects.create(name="Other", creator=self.alice)
        outsider = GamePlayer.objects.create(game=other, user=self.bob)
        services.send_message(self.game.pk, self.alice, self.round.pk, "Hello")
        with self.assertRaises(ValidationError):
            services.cast_vote(self.game.pk, self.alice, self.round.pk, outsider.pk)

    def test_next_round_and_stale_form(self):
        self.game.total_rounds = 2
        self.game.save(update_fields=["total_rounds"])
        next_round = self.close()
        self.assertEqual(next_round.number, 2)
        self.assertEqual(next_round.aliases.count(), 2)
        with self.assertRaises(ValidationError):
            services.send_message(self.game.pk, self.alice, self.round.pk, "Old form")

    def test_pages_and_private_feed(self):
        self.client.force_login(self.alice)
        services.send_message(self.game.pk, self.alice, self.round.pk, "Hello")
        self.assertEqual(self.client.get(reverse("game-detail", args=[self.game.pk])).status_code, 200)
        response = self.client.get(reverse("game-state", args=[self.game.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "alice")
        self.assertContains(response, "Hello")
        self.assertEqual(self.client.get(reverse("game-join", args=[self.game.pk])).status_code, 405)

    def test_finished_join(self):
        self.close()
        with self.assertRaises(ValidationError):
            services.join_game(self.game.pk, self.alice)

    def test_account_and_creation_pages(self):
        for name in ["login", "register", "game-home"]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(reverse("game-create")).status_code, 200)
        response = self.client.post(reverse("game-create"), {
            "name": "Solo", "short_description": "Created through the form",
            "total_rounds": 1, "round_duration_seconds": 30,
            "message_cooldown_seconds": 5, "max_message_length": 180, "min_players": 1,
        })
        self.assertEqual(response.status_code, 302)
        game = Game.objects.get(name="Solo")
        self.assertEqual(game.creator, self.alice)
        self.assertEqual(game.rounds.count(), 1)
