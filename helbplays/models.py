"""Server-side coordination for the personal external account. Assisted by OpenAI Codex."""
from django.db import models


class GatewayState(models.Model):
    last_attempt_at = models.DateTimeField(null=True, blank=True)
