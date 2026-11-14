"""Only this module knows the external chat protocol. Assisted by OpenAI Codex."""
import base64
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings

MAX_RESPONSE_BYTES = 2_000_000
REQUEST_TIMEOUT_SECONDS = 8


class ChatUnavailable(Exception):
    pass


def _read(url):
    try:
        with urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise ChatUnavailable("The chat response is too large.")
            return data.decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError):
        # Never expose the request URL: it contains the personal key.
        raise ChatUnavailable("The external chat is unavailable. Please try again later.") from None


def read_chat():
    return _read(settings.HELBPLAYS_CHAT_URL)


def send_message(content):
    if not settings.HELBPLAYS_UID or not settings.HELBPLAYS_KEY:
        raise ChatUnavailable("Configure the external account on the server first.")
    query = urlencode({"uid": settings.HELBPLAYS_UID, "key": settings.HELBPLAYS_KEY,
                       "message": base64.b64encode(content.encode("utf-8")).decode("ascii")})
    # GET is mandated by the external service. Do not log this URL or retry sends.
    return _read(settings.HELBPLAYS_SEND_URL + "?" + query)
