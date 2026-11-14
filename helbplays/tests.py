"""No real network traffic in tests. Assisted by OpenAI Codex."""
import base64
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit
from urllib.error import URLError
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from . import client, services
from .models import GatewayState, PokeClashAgent
from . import protocol
from .forms import AgentForm
from game.models import Script
from agents.services import Decision
from agents.providers import AgentProviderError, MODEL_CHOICES
from django.utils import timezone
from datetime import timedelta
import json

@override_settings(HELBPLAYS_UID="123", HELBPLAYS_KEY="private-test-key")
class ExternalChatTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("owner", is_staff=True)
        self.visitor = get_user_model().objects.create_user("visitor")

    @patch("helbplays.client.urlopen")
    def test_protocol(self, open_url):
        response = MagicMock()
        response.read.return_value = b"OK"
        open_url.return_value.__enter__.return_value = response
        services.send_message(self.owner, "Hello + / é")
        query = parse_qs(urlsplit(open_url.call_args.args[0]).query)
        self.assertEqual(query["uid"], ["123"])
        self.assertEqual(base64.b64decode(query["message"][0]).decode(), "Hello + / é")
        self.assertEqual(open_url.call_args.kwargs["timeout"], 8)

    @patch("helbplays.client.send_message")
    def test_cooldown(self, send):
        services.send_message(self.owner, "first")
        with self.assertRaises(ValidationError):
            services.send_message(self.owner, "second")
        send.assert_called_once()

    @patch("helbplays.client.send_message")
    def test_unauthorized_user(self, send):
        with self.assertRaises(PermissionDenied):
            services.send_message(self.visitor, "Hello")
        send.assert_not_called()

    @patch("helbplays.client.urlopen", side_effect=URLError("private-test-key"))
    def test_error_redaction(self, open_url):
        with self.assertRaises(client.ChatUnavailable) as error:
            client.send_message("Hello")
        self.assertNotIn("private-test-key", str(error.exception))

    @patch("helbplays.client.read_chat", return_value="<script>alert(1)</script>")
    @patch("helbplays.client.send_message")
    def test_polling_never_sends(self, send, read):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("helbplays-chat")).status_code, 200)
        response = self.client.get(reverse("helbplays-feed"))
        self.assertEqual(response.json()["content"], "<script>alert(1)</script>")
        send.assert_not_called()
        self.assertNotContains(response, "private-test-key")


class ProtocolTests(TestCase):
    def test_plaintext_semicolons_brackets_and_no_base64_guessing(self):
        data = protocol.parse_chat("[123;2026-11-14 12:00;hello; world [x]]\n[7;123;SGVsbG8=]\nmalformed")
        self.assertEqual(data["messages"][0]["message"], "hello; world [x]")
        self.assertEqual(data["messages"][1]["message"], "SGVsbG8=")
        self.assertEqual(data["ignored_lines"], 1)
        self.assertFalse(data["history_complete"])
        self.assertIsNone(data["round_start"])
        self.assertIsNone(data["scores"])

    def test_context_bounded_and_counts_are_only_observations(self):
        content = "\n".join(f"[{'u'*100}{i};{'t'*100};{'a'*2000}{i}]" for i in range(100))
        context = protocol.observations(content)
        context.update({"rules": protocol.RULES})
        self.assertLess(len(json.dumps(context)), 12000)
        self.assertEqual(len(context["messages"]), 20)
        self.assertIn("not verified current-round", context["observation_note"])


@override_settings(HELBPLAYS_UID="123", HELBPLAYS_KEY="private-test-key", HELBPLAYS_OWNER_USERNAME="")
class PokeClashAgentTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("owner", is_staff=True)
        self.other = get_user_model().objects.create_user("other", is_staff=True)
        self.visitor = get_user_model().objects.create_user("visitor")
        self.agent = PokeClashAgent.objects.create(owner=self.owner, enabled=True,
            model_name=MODEL_CHOICES["local"][0][0])
        GatewayState.objects.create(pk=1, active_agent=self.agent)

    def config(self, **changes):
        data = {field: getattr(self.agent, field) for field in
                ("enabled", "agent_type", "model_name", "prompt", "script", "interval_seconds")}
        data.update(changes)
        return data

    @patch("helbplays.client.read_chat", return_value="[1;123;blue]\n[2;124;blue]")
    @patch("agents.providers.generate_decision", return_value=Decision(message="blue"))
    @patch("helbplays.client.send_message")
    def test_worker_generates_with_rules_and_shared_cooldown(self, send, generate, read):
        result = services.run_pokeclash_agents()
        self.assertIn("Request sent", result[0])
        send.assert_called_once_with("blue")
        context = generate.call_args.args[3]
        self.assertIn("300 seconds", context["rules"])
        self.assertIsNone(context["scores"])
        self.assertNotIn("private-test-key", json.dumps(context))
        with self.assertRaises(ValidationError):
            services.send_message(self.owner, "human")
        self.assertEqual(services.run_pokeclash_agents(), [])

    @patch("helbplays.client.read_chat", return_value="[1;123;reset]")
    @patch("agents.providers.generate_decision", return_value=Decision(message=" ReSeT "))
    @patch("helbplays.client.send_message")
    def test_automatic_reset_is_blocked(self, send, generate, read):
        self.assertIn("blocked", services.run_pokeclash_agents()[0])
        send.assert_not_called()
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.failure_count, 1)
        self.assertGreater(self.agent.next_run_at, timezone.now() + timedelta(seconds=45))

    @patch("helbplays.client.send_message")
    def test_human_can_intentionally_reset(self, send):
        services.send_message(self.owner, "reset")
        send.assert_called_once_with("reset")

    @patch("helbplays.client.read_chat", return_value="")
    @patch("helbplays.client.send_message")
    def test_disable_while_thinking_discards_result(self, send, read):
        def generate(*args):
            services.save_agent(self.owner, self.config(enabled=False))
            return Decision(message="blue")
        with patch("agents.providers.generate_decision", side_effect=generate):
            self.assertIn("discarded", services.run_pokeclash_agents()[0])
        send.assert_not_called()

    @patch("helbplays.client.read_chat", return_value="")
    @patch("helbplays.client.send_message")
    def test_script_change_while_thinking_discards_result(self, send, read):
        script = Script.objects.create(owner=self.owner, title="Strategy", content="blue")
        self.agent.script = script
        self.agent.save()
        def generate(*args):
            Script.objects.filter(pk=script.pk).update(content="green")
            return Decision(message="blue")
        with patch("agents.providers.generate_decision", side_effect=generate):
            self.assertIn("discarded", services.run_pokeclash_agents()[0])
        send.assert_not_called()
        self.assertFalse(GatewayState.objects.get(pk=1).lease_token)

    @patch("helbplays.client.read_chat", return_value="")
    @patch("helbplays.client.send_message")
    def test_manual_action_during_thinking_invalidates_decision(self, send, read):
        def generate(*args):
            services.send_message(self.owner, "human")
            return Decision(message="blue")
        with patch("agents.providers.generate_decision", side_effect=generate):
            self.assertIn("discarded", services.run_pokeclash_agents()[0])
        send.assert_called_once_with("human")
        self.agent.refresh_from_db()
        self.assertIn("superseded", self.agent.last_result)

    @patch("agents.providers.generate_decision")
    @patch("helbplays.client.read_chat")
    def test_active_lease_prevents_duplicate_inference(self, read, generate):
        GatewayState.objects.filter(pk=1).update(lease_token="other-worker",
            lease_expires_at=timezone.now() + timedelta(minutes=1))
        self.assertIn("already in progress", services.run_pokeclash_agent(self.owner.pk))
        read.assert_not_called()
        generate.assert_not_called()

    @patch("helbplays.client.read_chat", return_value="")
    @patch("agents.providers.generate_decision", side_effect=AgentProviderError("private-test-key"))
    @patch("helbplays.client.send_message")
    def test_provider_error_has_backoff_and_redacted_status(self, send, generate, read):
        result = services.run_pokeclash_agents()[0]
        self.assertNotIn("private-test-key", result)
        self.assertIn("retry is delayed", result)
        send.assert_not_called()
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.failure_count, 1)

    @patch("helbplays.client.read_chat", return_value="")
    @patch("agents.providers.generate_decision", return_value=Decision(message="blue"))
    @patch("helbplays.client.send_message", side_effect=client.ChatUnavailable("private-test-key"))
    def test_uncertain_delivery_is_reserved_and_not_retried(self, send, generate, read):
        self.assertIn("uncertain", services.run_pokeclash_agents()[0])
        self.assertEqual(services.run_pokeclash_agents(), [])
        self.assertIsNotNone(GatewayState.objects.get(pk=1).last_attempt_at)
        send.assert_called_once()

    def test_private_script_queryset_and_service_ownership(self):
        script = Script.objects.create(owner=self.other, title="Private", content="private strategy")
        form = AgentForm(owner=self.owner)
        self.assertNotIn(script, form.fields["script"].queryset)
        with self.assertRaises(ValidationError):
            services.save_agent(self.owner, self.config(script=script))

    def test_one_automatic_owner_per_external_account(self):
        with self.assertRaises(ValidationError):
            services.save_agent(self.other, self.config())

    @patch("agents.providers.generate_decision")
    @patch("helbplays.client.send_message")
    @patch("helbplays.client.read_chat")
    def test_http_one_off_request_only_queues(self, read, send, generate):
        self.agent.enabled = False
        self.agent.save()
        self.client.force_login(self.owner)
        response = self.client.post(reverse("helbplays-agent-run"))
        self.assertEqual(response.status_code, 302)
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.run_requested)
        self.assertFalse(self.agent.enabled)
        generate.assert_not_called()
        read.assert_not_called()
        send.assert_not_called()

    @patch("helbplays.client.read_chat", return_value="")
    @patch("agents.providers.generate_decision", return_value=Decision(message="blue"))
    @patch("helbplays.client.send_message")
    def test_worker_consumes_one_off_without_enabling_automation(self, send, generate, read):
        self.agent.enabled = False
        self.agent.save()
        services.request_agent_run(self.owner)
        self.assertIn("Request sent", services.run_pokeclash_agents()[0])
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.enabled)
        self.assertFalse(self.agent.run_requested)
        self.assertEqual(services.run_pokeclash_agents(), [])
        send.assert_called_once_with("blue")

    @override_settings(HELBPLAYS_OWNER_USERNAME="visitor")
    @patch("helbplays.client.send_message")
    def test_explicit_nonstaff_owner_and_staff_restriction(self, send):
        services.send_message(self.visitor, "blue")
        send.assert_called_once_with("blue")
        with self.assertRaises(PermissionDenied):
            services.send_message(self.owner, "blue")

    @patch("agents.providers.generate_decision")
    @patch("helbplays.client.send_message")
    def test_unauthorized_posts_and_configuration_do_not_act(self, send, generate):
        self.client.force_login(self.visitor)
        for url in ("helbplays-agent", "helbplays-agent-run", "helbplays-send"):
            self.assertEqual(self.client.post(reverse(url), {"content": "blue"}).status_code, 403)
        generate.assert_not_called()
        send.assert_not_called()

    @override_settings(HELBPLAYS_UID="", HELBPLAYS_KEY="")
    @patch("agents.providers.generate_decision")
    @patch("helbplays.client.read_chat")
    @patch("helbplays.client.send_message")
    def test_setup_state_does_not_send_or_enable(self, send, read, generate):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("helbplays-chat"))
        self.assertContains(response, "Account setup required")
        self.assertContains(response, "HELBPLAYS_UID")
        self.assertNotContains(response, "private-test-key")
        with self.assertRaises(ValidationError):
            services.save_agent(self.owner, self.config())
        services.run_pokeclash_agents()
        read.assert_not_called()
        generate.assert_not_called()
        send.assert_not_called()
