from __future__ import annotations

from .models import CreatureRef


def enemy_ref(enemy_index: int) -> str:
    return f"enemy:{enemy_index}"


def enemy_index(actor_ref: CreatureRef) -> int:
    prefix = "enemy:"
    if not actor_ref.startswith(prefix):
        raise ValueError(f"'{actor_ref}' is not an enemy creature reference.")
    return int(actor_ref[len(prefix):])


def reroll_die_action_id(action_id: str, die_index: int) -> str:
    return f"{action_id}-reroll-damage-{die_index}"
