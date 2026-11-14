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
