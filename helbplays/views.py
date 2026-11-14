"""Read-only polling is independent from sending. Assisted by OpenAI Codex."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST
from agents.providers import provider_status
from . import client, services, protocol
from .forms import AgentForm
from .models import PokeClashAgent


def _chat_context(user, form=None):
    allowed = services.can_control(user)
    agent = PokeClashAgent.objects.filter(owner=user).first() if allowed else None
    instance = agent or PokeClashAgent(owner=user)
    return {"can_control": allowed, "account_ready": services.account_ready(),
            "agent": agent, "agent_form": form or (AgentForm(owner=user, instance=instance) if allowed else None),
            "provider_issue": provider_status(instance.agent_type) if allowed else ""}


@login_required
def chat(request):
    return render(request, "helbplays/chat.html", _chat_context(request.user))


@login_required
@require_GET
def feed(request):
    try:
        content = client.read_chat()
        response = JsonResponse({"content": content, **protocol.parse_chat(content)})
    except client.ChatUnavailable as error:
        response = JsonResponse({"error": str(error)}, status=502)
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_POST
def send(request):
    try:
        services.send_message(request.user, request.POST.get("content", ""))
        messages.info(request, "Request sent. Check the chat for confirmation.")
    except ValidationError as error:
        messages.error(request, error.messages[0])
    except client.ChatUnavailable as error:
        messages.error(request, str(error))
    return redirect("helbplays-chat")


@login_required
@require_POST
def configure_agent(request):
    if not services.can_control(request.user):
        raise PermissionDenied
    instance = PokeClashAgent.objects.filter(owner=request.user).first() or PokeClashAgent(owner=request.user)
    form = AgentForm(request.POST, owner=request.user, instance=instance)
    if form.is_valid():
        try:
            services.save_agent(request.user, form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, "PokeClash agent settings saved.")
            return redirect("helbplays-chat")
    return render(request, "helbplays/chat.html", _chat_context(request.user, form), status=400)


@login_required
@require_POST
def run_agent(request):
    if not services.can_control(request.user):
        raise PermissionDenied
    try:
        services.request_agent_run(request.user)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.info(request, "One agent decision queued. Run the server worker to process it.")
    return redirect("helbplays-chat")
