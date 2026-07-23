from __future__ import annotations

from .models import CreatureRef


def enemy_ref(enemy_index: int) -> str:
    return f"enemy:{enemy_index}"


def enemy_index(creature_ref: CreatureRef) -> int:
    prefix = "enemy:"
    if not creature_ref.startswith(prefix):
        raise ValueError(f"'{creature_ref}' is not an enemy creature reference.")
    return int(creature_ref[len(prefix):])


def reroll_die_action_id(action_id: str, die_index: int) -> str:
    return f"{action_id}-reroll-damage-{die_index}"
