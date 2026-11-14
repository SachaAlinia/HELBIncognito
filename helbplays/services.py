"""One shared account, cooldown and inference lease for human and model actions."""
import os
import uuid
from datetime import timedelta
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone
from . import client, protocol
from .models import GatewayState, PokeClashAgent


def can_control(user):
    owner = getattr(settings, "HELBPLAYS_OWNER_USERNAME", os.environ.get("HELBPLAYS_OWNER_USERNAME", ""))
    return bool(user.is_authenticated and user.is_active and
                (user.get_username() == owner if owner else user.is_staff))


def account_ready():
    return bool(settings.HELBPLAYS_UID and settings.HELBPLAYS_KEY)


def _gateway():
    GatewayState.objects.get_or_create(pk=1)
    # Force SQLite's write lock as well as PostgreSQL's row lock.
    GatewayState.objects.filter(pk=1).update(id=1)
    return GatewayState.objects.select_for_update().get(pk=1)


def _cooldown(state, now):
    delay = max(10, settings.HELBPLAYS_COOLDOWN_SECONDS)
    if state.last_attempt_at and now < state.last_attempt_at + timedelta(seconds=delay):
        raise ValidationError(f"Wait {delay} seconds between sending attempts.")


def _validate_message(content):
    if not isinstance(content, str) or not content.strip():
        raise ValidationError("Enter a message.")
    if len(content) > 2000:
        raise ValidationError("Messages must be at most 2000 characters.")


def send_message(user, content):
    if not can_control(user):
        raise PermissionDenied
    _validate_message(content)
    if not account_ready():
        raise client.ChatUnavailable("Configure HELBPLAYS_UID and HELBPLAYS_KEY on the server first.")
    with transaction.atomic():
        state = _gateway()
        now = timezone.now()
        _cooldown(state, now)
        state.last_attempt_at = now
        # A human action supersedes any model currently thinking.
        state.lease_token = ""
        state.lease_expires_at = None
        state.save()
    # Reserve first: a timeout can mean delivery succeeded. Never retry this send.
    return client.send_message(content)


def save_agent(user, cleaned_data):
    if not can_control(user):
        raise PermissionDenied
    with transaction.atomic():
        state = _gateway()
        agent, _ = PokeClashAgent.objects.get_or_create(owner=user)
        if cleaned_data["enabled"]:
            if not account_ready():
                raise ValidationError("Configure HELBPLAYS_UID and HELBPLAYS_KEY before enabling the agent.")
            if state.active_agent_id and state.active_agent_id != agent.pk:
                other = PokeClashAgent.objects.filter(pk=state.active_agent_id, enabled=True).first()
                if other and can_control(other.owner):
                    raise ValidationError("Another owner already controls the configured account. Disable that agent first.")
            state.active_agent = agent
        elif state.active_agent_id == agent.pk:
            state.active_agent = None
        script = cleaned_data.get("script")
        if script and script.owner_id != user.pk:
            raise ValidationError("Choose one of your own scripts.")
        for field in ("enabled", "agent_type", "model_name", "prompt", "script", "interval_seconds"):
            setattr(agent, field, cleaned_data[field])
        agent.revision += 1
        agent.next_run_at = timezone.now()
        agent.failure_count = 0
        agent.run_requested = False
        agent.last_result = "Configuration saved. Run the worker to process enabled agents."
        agent.save()
        state.lease_token = ""
        state.lease_expires_at = None
        state.save()
        return agent


def request_agent_run(user):
    """Queue one decision; HTTP never performs model inference."""
    if not can_control(user):
        raise PermissionDenied
    with transaction.atomic():
        state = _gateway()
        agent = PokeClashAgent.objects.filter(owner=user).first()
        if not agent:
            raise ValidationError("Save your agent settings first.")
        if not account_ready():
            raise ValidationError("Configure HELBPLAYS_UID and HELBPLAYS_KEY on the server first.")
        if state.active_agent_id and state.active_agent_id != agent.pk:
            raise ValidationError("Another agent controls the configured account.")
        now = timezone.now()
        _cooldown(state, now)
        if state.lease_token and state.lease_expires_at and state.lease_expires_at > now:
            raise ValidationError("An agent decision is already in progress.")
        if agent.failure_count and agent.next_run_at and agent.next_run_at > now:
            raise ValidationError("The agent is waiting after an error. Try again after its next eligible attempt.")
        agent.run_requested = True
        agent.next_run_at = now
        agent.last_result = "One decision queued. Start the worker to process it."
        agent.save(update_fields=["run_requested", "next_run_at", "last_result"])


def _snapshot(agent):
    script = agent.script
    if script and script.owner_id != agent.owner_id:
        raise ValidationError("The selected script must belong to this account owner.")
    return (agent.revision, agent.agent_type, agent.model_name, agent.prompt,
            script.pk if script else None, script.content if script else "", agent.interval_seconds)


def _finish(agent_id, token, result, failed=False):
    with transaction.atomic():
        state = _gateway()
        if state.lease_token != token:
            if not state.lease_token:
                superseded = PokeClashAgent.objects.filter(pk=agent_id, last_result="Generating a decision…").first()
                if superseded:
                    superseded.last_result = "Decision superseded by a manual action."
                    superseded.next_run_at = timezone.now() + timedelta(seconds=max(10, superseded.interval_seconds))
                    superseded.save(update_fields=["last_result", "next_run_at"])
            return
        agent = PokeClashAgent.objects.get(pk=agent_id)
        agent.failure_count = min(agent.failure_count + 1, 8) if failed else 0
        delay = min(1800, max(10, agent.interval_seconds) * (2 ** agent.failure_count))
        agent.next_run_at = timezone.now() + timedelta(seconds=delay)
        agent.last_result = result
        agent.save(update_fields=["failure_count", "next_run_at", "last_result"])
        state.lease_token = ""
        state.lease_expires_at = None
        state.save(update_fields=["lease_token", "lease_expires_at"])


def run_pokeclash_agent(owner_id, *, manual_run=False):
    from agents import providers
    token = uuid.uuid4().hex
    with transaction.atomic():
        state = _gateway()
        agent = PokeClashAgent.objects.select_related("owner", "script").filter(owner_id=owner_id).first()
        now = timezone.now()
        if not agent or not can_control(agent.owner):
            return "Account owner is not authorized."
        manual_run = manual_run or agent.run_requested
        if not manual_run and (not agent.enabled or state.active_agent_id != agent.pk):
            return "Agent is disabled."
        if state.active_agent_id and state.active_agent_id != agent.pk:
            return "Another agent controls the configured account."
        if not account_ready():
            return "Configure HELBPLAYS_UID and HELBPLAYS_KEY on the server first."
        if state.lease_token and state.lease_expires_at and state.lease_expires_at > now:
            return "An agent decision is already in progress."
        if not manual_run and agent.next_run_at and agent.next_run_at > now:
            return "Agent is waiting for its next scheduled decision."
        try:
            _cooldown(state, now)
            snapshot = _snapshot(agent)
        except ValidationError as error:
            return error.messages[0]
        state.lease_token = token
        state.lease_expires_at = now + timedelta(minutes=5)
        state.save()
        agent.last_run_at = now
        agent.run_requested = False
        agent.next_run_at = state.lease_expires_at
        agent.last_result = "Generating a decision…"
        agent.save(update_fields=["last_run_at", "next_run_at", "last_result", "run_requested"])
    try:
        context = {"game": "pokeclash", "rules": protocol.RULES, "max_message_length": 180,
                   "allowed_target_ids": []}
        context.update(protocol.observations(client.read_chat()))
        prompt = "\n\n".join(part for part in (snapshot[5][:800], snapshot[3][:1198]) if part)
        decision = providers.generate_decision(snapshot[1], snapshot[2], prompt, context)
        content = decision.message
        if not content:
            _finish(agent.pk, token, "Agent chose to wait.")
            return "Agent chose to wait."
        _validate_message(content)
        if content.strip().casefold() == "reset":
            raise ValidationError("Automated reset messages are blocked. Use manual sending for an intentional reset.")
        with transaction.atomic():
            state = _gateway()
            current = PokeClashAgent.objects.select_related("owner", "script").get(pk=agent.pk)
            now = timezone.now()
            if (state.lease_token != token or not state.lease_expires_at or
                    state.lease_expires_at <= now or _snapshot(current) != snapshot or
                    not can_control(current.owner) or
                    (not manual_run and (not current.enabled or state.active_agent_id != current.pk))):
                result = "Configuration changed or the decision lease expired; decision discarded."
                _finish(agent.pk, token, result)
                return result
            if not account_ready():
                raise client.ChatUnavailable("Configure the external account on the server first.")
            _cooldown(state, now)
            state.last_attempt_at = now
            state.save(update_fields=["last_attempt_at"])
        # Retain the lease throughout the request; shared cooldown blocks human sends too.
        client.send_message(content)
        result = "Request sent. Check the chat for confirmation."
        _finish(agent.pk, token, result)
        return result
    except providers.AgentProviderError:
        result = "Model unavailable or invalid response. Check provider setup; retry is delayed."
    except client.ChatUnavailable:
        result = "External chat unavailable. Delivery may be uncertain; no send is retried."
    except ValidationError as error:
        result = error.messages[0]
    except Exception:
        result = "Agent decision failed. Check server setup; retry is delayed."
    # Never expose model output, credentials, provider URLs or raw exceptions in status.
    _finish(agent.pk, token, result, failed=True)
    return result


def run_pokeclash_agents(limit=10):
    now = timezone.now()
    owners = list(PokeClashAgent.objects.filter(models.Q(enabled=True) | models.Q(run_requested=True)).filter(
        models.Q(next_run_at__isnull=True) | models.Q(next_run_at__lte=now)
    ).values_list("owner_id", flat=True)[:limit])
    return [run_pokeclash_agent(owner_id) for owner_id in owners]
