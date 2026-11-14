"""Agents must use the same rules as human players. Assisted by OpenAI Codex."""
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from game.models import Game
from game import services as game_services
from .services import Decision, play_incognito, play_pokeclash


class AgentActionsTests(TestCase):
    def test_incognito_agent_obeys_cooldown(self):
        user = get_user_model().objects.create_user("agent")
        game = Game.objects.create(name="Agent game", creator=user, min_players=1)
        player = game_services.join_game(game.pk, user)
        player.ai_enabled = True
        round_ = game.rounds.get()
        play_incognito(player, round_.pk, Decision(message="Hello"))
        with self.assertRaises(ValidationError):
            play_incognito(player, round_.pk, Decision(message="Again"))

    @patch("agents.services.helbplays_services.send_message")
    def test_external_agent_uses_shared_gateway(self, send):
        user = get_user_model().objects.create_user("agent")
        play_pokeclash(user, Decision(message="Hello"))
        send.assert_called_once_with(user, "Hello")
