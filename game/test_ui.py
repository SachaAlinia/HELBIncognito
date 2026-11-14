"""HTTP ownership and game-control regressions. Assisted by OpenAI Codex."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from agents.providers import MODEL_CHOICES
from . import services
from .models import Game, GamePlayer, Script


class GameInterfaceTests(TestCase):
    def setUp(self):
        self.alice = get_user_model().objects.create_user("alice")
        self.bob = get_user_model().objects.create_user("bob")
        self.game = Game.objects.create(name="Interface", creator=self.alice, total_rounds=2)
        self.a = services.join_game(self.game.pk, self.alice)
        self.b = services.join_game(self.game.pk, self.bob)
        self.round = self.game.rounds.get()
        self.client.force_login(self.alice)

    def test_script_library_crud_and_ownership(self):
        secret = Script.objects.create(owner=self.bob, title="Private", content="Do not expose")
        response = self.client.post(reverse("script-create"), {"title": "Helpful", "content": "Be concise", "owner": self.bob.pk})
        self.assertRedirects(response, reverse("script-list"))
        own = Script.objects.get(title="Helpful")
        self.assertEqual(own.owner, self.alice)
        self.assertNotContains(self.client.get(reverse("script-list")), "Do not expose")
        for route in ["script-edit", "script-delete"]:
            self.assertEqual(self.client.post(reverse(route, args=[secret.pk]), {"title": "Changed", "content": "Changed"}).status_code, 404)
        self.assertEqual(self.client.get(reverse("script-delete", args=[own.pk])).status_code, 405)
        self.client.post(reverse("script-edit", args=[own.pk]), {"title": "Updated", "content": "New prompt"})
        own.refresh_from_db()
        self.assertEqual(own.content, "New prompt")
        self.client.post(reverse("script-delete", args=[own.pk]))
        self.assertFalse(Script.objects.filter(pk=own.pk).exists())

    def config(self, **changes):
        data = {"ai_enabled": "on", "ai_agent_type": "local", "ai_model_name": MODEL_CHOICES["local"][0][0], "ai_prompt": "Personal prompt"}
        data.update(changes)
        return self.client.post(reverse("game-agent", args=[self.game.pk]), data)

    def test_config_owned_player_script_copy_and_revision(self):
        script = Script.objects.create(owner=self.alice, title="Own", content="Script prompt")
        self.a.ai_lease_token = "active-lease"
        self.a.ai_last_error = "Old failure"
        self.a.ai_failure_count = 3
        self.a.ai_next_run_at = timezone.now() + timedelta(minutes=5)
        self.a.save()
        self.config(script=script.pk, player_id=self.b.pk)
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertTrue(self.a.ai_enabled)
        self.assertFalse(self.b.ai_enabled)
        self.assertEqual(self.a.ai_prompt, "Script prompt\n\nPersonal prompt")
        self.assertEqual(self.a.ai_config_revision, 1)
        self.assertEqual(self.a.ai_last_error, "")
        self.assertIsNone(self.a.ai_next_run_at)
        self.assertEqual(self.a.ai_failure_count, 0)
        self.assertEqual(self.a.ai_lease_token, "active-lease")
        self.client.post(reverse("game-agent", args=[self.game.pk]), {"action": "stop"})
        self.a.refresh_from_db()
        self.assertFalse(self.a.ai_enabled)
        self.assertEqual(self.a.ai_config_revision, 2)
        self.assertEqual(self.a.ai_lease_token, "active-lease")

    def test_foreign_script_and_cross_provider_model_rejected(self):
        script = Script.objects.create(owner=self.bob, title="Foreign", content="Secret")
        self.config(script=script.pk)
        self.a.refresh_from_db()
        self.assertFalse(self.a.ai_enabled)
        self.config(ai_agent_type="api", ai_model_name=MODEL_CHOICES["local"][0][0])
        self.a.refresh_from_db()
        self.assertFalse(self.a.ai_enabled)
        self.assertEqual(self.a.ai_prompt, "")

    def test_script_plus_prompt_limit_and_api_switch(self):
        script = Script.objects.create(owner=self.alice, title="Long", content="s" * 1990)
        self.config(script=script.pk, ai_prompt="p" * 20)
        self.a.refresh_from_db()
        self.assertFalse(self.a.ai_enabled)
        self.config(ai_agent_type="api", ai_model_name=MODEL_CHOICES["api"][0][0])
        self.a.refresh_from_db()
        self.assertTrue(self.a.ai_enabled)
        self.assertEqual(self.a.ai_agent_type, "api")
        self.assertEqual(self.a.ai_model_name, MODEL_CHOICES["api"][0][0])

    def test_poll_status_is_scoped_to_current_player(self):
        self.a.ai_last_error = "Alice status"
        self.a.save(update_fields=["ai_last_error"])
        self.b.ai_last_error = "Bob private status"
        self.b.save(update_fields=["ai_last_error"])
        response = self.client.get(reverse("game-state", args=[self.game.pk]))
        self.assertEqual(response.json()["own_agent"]["error"], "Alice status")
        self.assertNotContains(response, "Bob private status")

    def test_agent_nonplayer_and_get_rejected_and_csrf_required(self):
        url = reverse("game-agent", args=[self.game.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        outsider = get_user_model().objects.create_user("outsider")
        self.client.force_login(outsider)
        self.assertEqual(self.client.post(url, {"action": "stop"}).status_code, 404)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.alice)
        self.assertEqual(csrf_client.post(url, {"action": "stop"}).status_code, 403)

    def test_message_vote_ui_and_current_alias(self):
        url = reverse("game-action", args=[self.game.pk])
        data = {"round_id": self.round.pk, "action": "message", "content": "Hello"}
        self.client.post(url, data)
        self.assertFalse(self.round.messages.exists())
        self.client.post(url, {**data, "target": self.b.pk})
        self.assertEqual(self.round.messages.count(), 1)
        self.assertEqual(self.round.votes.get(voter=self.a).target_id, self.b.pk)
        response = self.client.get(reverse("game-detail", args=[self.game.pk]))
        self.assertContains(response, "round-countdown")
        self.assertContains(response, self.round.aliases.get(player=self.a).alias)
        self.assertEqual(response.context["vote_alias"], self.round.aliases.get(player=self.b).alias)
        self.assertContains(response, reverse("public-profile", args=[self.bob.pk]))

    def test_history_preserves_zero_and_nonparticipation(self):
        services.send_message(self.game.pk, self.alice, self.round.pk, "Hello", target_id=self.b.pk)
        services.advance_game(self.game.pk, self.round.started_at + timedelta(seconds=121))
        late = get_user_model().objects.create_user("late")
        late_player = services.join_game(self.game.pk, late)
        response = self.client.get(reverse("game-detail", args=[self.game.pk]))
        scores = {score["player"].pk: score for score in response.context["history"][0]["scores"]}
        self.assertTrue(scores[self.a.pk]["participated"])
        self.assertEqual(scores[self.a.pk]["points"], 0)
        self.assertEqual(scores[self.b.pk]["points"], 1)
        self.assertFalse(scores[late_player.pk]["participated"])
        self.assertContains(response, "Did not participate")
