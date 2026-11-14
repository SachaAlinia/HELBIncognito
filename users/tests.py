"""Profile regression tests. Assisted by OpenAI Codex."""
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import Profile

class ProfileTests(TestCase):
    @patch("PIL.Image.open", side_effect=AssertionError("Unexpected image processing"))
    def test_save_does_not_open_avatar(self, image_open):
        user = get_user_model().objects.create_user("alice")
        self.assertTrue(Profile.objects.filter(user=user).exists())
        user.email = "alice@example.com"
        user.save(update_fields=["email"])
        user.profile.save(update_fields=["image"])

    def test_missing_legacy_profile(self):
        user = get_user_model().objects.create_user("alice")
        Profile.objects.filter(user=user).delete()
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)

    def test_logout(self):
        user = get_user_model().objects.create_user("alice")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("logout")).status_code, 200)
