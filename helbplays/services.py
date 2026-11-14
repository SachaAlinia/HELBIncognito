"""Shared manual/agent sending policy. Assisted by OpenAI Codex."""
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from . import client
from .models import GatewayState


def send_message(user, content):
    # A single personal account is configured: ordinary site users cannot use it.
    if not user.is_active or not user.is_staff:
        raise PermissionDenied
    if not content.strip():
        raise ValidationError("Enter a message.")
    if not settings.HELBPLAYS_UID or not settings.HELBPLAYS_KEY:
        raise client.ChatUnavailable("Configure the external account on the server first.")
    with transaction.atomic():
        GatewayState.objects.get_or_create(pk=1)
        GatewayState.objects.filter(pk=1).update(id=1)
        state = GatewayState.objects.select_for_update().get(pk=1)
        now = timezone.now()
        if state.last_attempt_at and now < state.last_attempt_at + timedelta(seconds=settings.HELBPLAYS_COOLDOWN_SECONDS):
            raise ValidationError("Wait ten seconds between sending attempts.")
        state.last_attempt_at = now
        state.save(update_fields=["last_attempt_at"])
    # Reserve before the request. A timeout may mean delivery succeeded; no automatic retry.
    return client.send_message(content)
