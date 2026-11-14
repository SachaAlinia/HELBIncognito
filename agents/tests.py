"""Agents must use the same rules as human players. Assisted by OpenAI Codex."""
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, TransactionTestCase
from django.db import connection
from django.core.management import call_command
from django.utils import timezone
from django.test import override_settings
from game.models import Game, GamePlayer, Message, Vote
from game import services as game_services
from .services import Decision, play_incognito, play_pokeclash
from . import providers, worker


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


class AgentWorkerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("private-username")
        other = get_user_model().objects.create_user("other-private-name")
        self.game = Game.objects.create(name="Agents", creator=self.user)
        self.player = game_services.join_game(self.game.pk, self.user)
        self.target = game_services.join_game(self.game.pk, other)
        GamePlayer.objects.filter(pk=self.player.pk).update(
            ai_enabled=True, ai_agent_type="api", ai_model_name="openai/gpt-oss-20b")
        self.round = self.game.rounds.get()
        self.decision = Decision(message="Hello", target_id=self.target.pk)

    @patch("agents.worker.generate_decision")
    def test_opt_in_and_atomic_vote(self, generate):
        generate.return_value = self.decision
        self.assertEqual(worker.run_incognito_agents(), 1)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(Vote.objects.get().target_id, self.target.pk)
        self.assertEqual(generate.call_count, 1)
        self.assertNotIn("private", str(generate.call_args))
        worker.run_incognito_agents()
        self.assertEqual(generate.call_count, 1)

    @patch("agents.worker.generate_decision")
    def test_disabled_and_dry_run_do_not_infer_or_write(self, generate):
        out = StringIO()
        call_command("run_agents", once=True, dry_run=True, stdout=out)
        self.assertIn("1 eligible", out.getvalue())
        self.player.refresh_from_db()
        self.assertFalse(self.player.ai_lease_token)
        self.assertIsNone(self.player.ai_next_run_at)
        GamePlayer.objects.filter(pk=self.player.pk).update(ai_enabled=False)
        self.assertEqual(worker.run_incognito_agents(), 0)
        generate.assert_not_called()

    @patch("agents.worker.generate_decision")
    def test_disable_and_config_changes_discard_inflight_decision(self, generate):
        def disable(*args):
            GamePlayer.objects.filter(pk=self.player.pk).update(ai_enabled=False, ai_config_revision=1)
            return self.decision
        generate.side_effect = disable
        self.assertEqual(worker.run_incognito_agents(), 0)
        self.assertFalse(Message.objects.exists())
        self.assertFalse(Vote.objects.exists())
        self.player.refresh_from_db()
        self.assertFalse(self.player.ai_lease_token)

    @patch("agents.worker.generate_decision")
    def test_stale_round_discards_inflight_decision(self, generate):
        def expire(*args):
            self.game.rounds.update(started_at=timezone.now() - timedelta(seconds=121))
            return self.decision
        generate.side_effect = expire
        self.assertEqual(worker.run_incognito_agents(), 0)
        self.assertFalse(Message.objects.exists())

    def test_atomic_lease_and_fencing(self):
        first = worker._claim(self.player.pk)
        self.assertIsNotNone(first)
        self.assertIsNone(worker._claim(self.player.pk))
        GamePlayer.objects.filter(pk=self.player.pk).update(ai_lease_until=timezone.now() - timedelta(seconds=1))
        second = worker._claim(self.player.pk)
        self.assertIsNotNone(second)
        self.assertFalse(worker._finish(first, decision=self.decision))
        self.assertTrue(worker._finish(second, decision=self.decision))
        self.assertEqual(Message.objects.count(), 1)

    @patch("agents.worker.generate_decision", side_effect=RuntimeError("secret-provider-key"))
    def test_failure_backoff_and_sanitized_error(self, generate):
        self.assertEqual(worker.run_incognito_agents(), 0)
        self.player.refresh_from_db()
        self.assertEqual(self.player.ai_failure_count, 1)
        self.assertGreater(self.player.ai_next_run_at, timezone.now())
        self.assertNotIn("secret", self.player.ai_last_error)
        worker.run_incognito_agents()
        self.assertEqual(generate.call_count, 1)

    @patch("agents.worker.generate_decision")
    def test_invalid_vote_never_posts_message(self, generate):
        generate.return_value = Decision(message="Hello", target_id=self.player.pk)
        worker.run_incognito_agents()
        self.assertFalse(Message.objects.exists())
        self.assertFalse(Vote.objects.exists())


class ProviderTests(TestCase):
    context = {"allowed_target_ids": [7], "max_message_length": 50}

    @override_settings(GROQ_API_KEY="")
    @patch("agents.providers.urlopen")
    def test_missing_key_does_not_call_api(self, urlopen):
        with self.assertRaisesMessage(providers.AgentProviderError, "GROQ_API_KEY"):
            providers.generate_decision("api", "openai/gpt-oss-20b", "", self.context)
        urlopen.assert_not_called()

    @override_settings(GROQ_API_KEY="test-secret")
    @patch("agents.providers.urlopen")
    def test_real_api_payload_and_response_interface(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"choices":[{"message":{"content":"{\\"message\\":\\"Hi\\",\\"target_id\\":7}"}}]}')
        result = providers.generate_decision("api", "openai/gpt-oss-20b", "Be kind", self.context)
        self.assertEqual(result, Decision(message="Hi", target_id=7))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(request.headers["Authorization"], "Bearer test-secret")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 30)

    @patch("agents.providers.provider_status", return_value="")
    @patch("agents.providers._local", return_value='{"message":"Hi","target_id":7}')
    def test_local_routes_to_real_provider_without_api(self, local, status):
        result = providers.generate_decision("local", providers.MODEL_CHOICES["local"][0][0], "", self.context)
        self.assertEqual(result.target_id, 7)
        local.assert_called_once()

    def test_rejects_unknown_model_and_invalid_decision(self):
        with self.assertRaises(providers.AgentProviderError):
            providers.generate_decision("local", "arbitrary-code-repository", "", self.context)
        for text in ['{"message":"Hi","target_id":8}', '{"message":"Hi","target_id":true}', "plain text"]:
            with self.assertRaises(providers.AgentProviderError):
                providers._parse(text, self.context)

    @patch("agents.providers._load_local")
    def test_local_bounds_prose_and_uses_model_scores_for_valid_vote(self, load):
        tokenizer, model, torch_stub = MagicMock(), MagicMock(), MagicMock()
        torch_stub.get_num_threads.return_value = 8
        tokenizer.return_value = {"input_ids": SimpleNamespace(shape=(1, 3))}
        tokenizer.decode.return_value = "Hello everyone"
        tokenizer.encode.side_effect = lambda label, **kwargs: [ord(label)]
        model.generate.return_value = [[0, 1, 2, 3]]
        model.return_value.logits.__getitem__.return_value.__getitem__.return_value.argmax.return_value.item.return_value = 1
        load.return_value = tokenizer, model
        context = {"game": "incognito", "allowed_target_ids": [7, 9],
                   "max_message_length": 5, "players": []}
        with patch.dict("sys.modules", {"torch": torch_stub}):
            result = providers._parse(providers._local("model", "", context), context)
        self.assertEqual(result, Decision(message="Hello", target_id=9))
        model.assert_called_once()  # A real model forward pass selects the vote.

    def test_exact_pokeclash_message_and_wait_are_preserved(self):
        context = {"game": "pokeclash", "allowed_target_ids": [], "max_message_length": 180}
        self.assertEqual(providers._parse('{"message":" hello ","target_id":null}', context).message, " hello ")
        self.assertEqual(providers._parse('{"message":"","target_id":null}', context).message, "")


class InferenceTransactionTests(TransactionTestCase):
    @patch("agents.worker.generate_decision")
    def test_inference_runs_after_database_transaction_is_released(self, generate):
        user = get_user_model().objects.create_user("solo-agent")
        game = Game.objects.create(name="Solo", creator=user, min_players=1)
        player = game_services.join_game(game.pk, user)
        GamePlayer.objects.filter(pk=player.pk).update(
            ai_enabled=True, ai_agent_type="api", ai_model_name="openai/gpt-oss-20b")
        def decide(*args):
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(GamePlayer.objects.get(pk=player.pk).ai_lease_token)
            return Decision(message="Hello")
        generate.side_effect = decide
        self.assertEqual(worker.run_incognito_agents(), 1)
