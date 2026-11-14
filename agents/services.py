"""Agent actions reuse human services. Assisted by OpenAI Codex.

Model inference belongs in a separate worker, never in chat polling requests.
Local/API model providers can supply decisions to these entry points.
"""
from dataclasses import dataclass
from game import services as game_services
from helbplays import services as helbplays_services


@dataclass(frozen=True)
class Decision:
    message: str = ""
    target_id: int | None = None


def play_incognito(player, round_id, decision):
    if not player.ai_enabled:
        return
    if decision.message:
        game_services.send_message(player.game_id, player.user, round_id, decision.message)
    if decision.target_id is not None:
        game_services.cast_vote(player.game_id, player.user, round_id, decision.target_id)


def play_pokeclash(user, decision):
    if decision.message:
        return helbplays_services.send_message(user, decision.message)
