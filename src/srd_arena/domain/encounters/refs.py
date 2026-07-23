from __future__ import annotations

from .models import CreatureRef


def participant_ref(participant_index: int) -> CreatureRef:
    return f"participant:{participant_index}"


def reroll_die_action_id(action_id: str, die_index: int) -> str:
    return f"{action_id}-reroll-damage-{die_index}"
