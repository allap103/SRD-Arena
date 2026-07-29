from __future__ import annotations

from typing import TYPE_CHECKING

from .models import Combatant

if TYPE_CHECKING:
    from .encounter import EncounterState


def movement_remaining(state: EncounterState, actor_ref: str) -> int:
    """Return the movement an actor can still spend on the current turn."""
    return state.turn_engine.movement_remaining(state, actor_ref)


def living_enemy_at(
    state: EncounterState, x: int, y: int
) -> Combatant | None:
    """Return the living enemy occupying a grid cell, if any."""
    return state.turn_engine.live_enemy_at(state, x, y)
