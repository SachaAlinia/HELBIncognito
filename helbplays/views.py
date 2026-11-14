"""Read-only polling is independent from sending. Assisted by OpenAI Codex."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST
from . import client, services


@login_required
def chat(request):
    return render(request, "helbplays/chat.html")


@login_required
@require_GET
def feed(request):
    try:
        response = JsonResponse({"content": client.read_chat()})
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
