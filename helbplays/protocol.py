"""Parse plaintext observations; the remote feed is not a complete game history."""
from collections import Counter

MAX_MESSAGES = 100
MAX_MESSAGE_LENGTH = 2000


def parse_chat(content, limit=MAX_MESSAGES):
    messages = []
    ignored = 0
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if not (line.startswith("[") and line.endswith("]")):
            ignored += 1
            continue
        fields = line[1:-1].split(";", 2)
        if len(fields) != 3 or not fields[0].strip() or not fields[1].strip():
            ignored += 1
            continue
        uid, timestamp, message = fields
        messages.append({"uid": uid.strip()[:100], "timestamp": timestamp.strip()[:100],
                         "message": message[:MAX_MESSAGE_LENGTH]})
    return {"messages": messages[-limit:], "ignored_lines": ignored,
            "history_complete": False, "round_start": None, "scores": None}


def observations(content):
    parsed = parse_chat(content, limit=20)
    for message in parsed["messages"]:
        message["uid"] = message["uid"][:40]
        message["timestamp"] = message["timestamp"][:40]
        message["message"] = message["message"][:180]
    latest = {}
    for message in parsed["messages"]:
        latest[message["uid"]] = message["message"]
    # These counts deliberately span the visible window, not an asserted current round.
    groups = Counter(latest.values())
    parsed["latest_observed_groups"] = [{"message": text, "count": count}
                                         for text, count in groups.most_common(8)]
    parsed["observation_note"] = (
        "The feed may be truncated. These are the last observed messages per UID in "
        "the visible window, not verified current-round groups. Round start and scores are unknown."
    )
    return parsed


RULES = (
    "PokeClash: a round lasts 300 seconds from its first message. Each participant's "
    "last message in that round selects their group. The uniquely largest group wins; "
    "each winner receives floor(number of losers / number of winners) points. A tie "
    "for largest group awards no points. A reset group of at least 25 participants "
    "at round end resets every score. Never infer a scoreboard or round boundaries "
    "from an incomplete feed. Automated reset messages are prohibited."
)
