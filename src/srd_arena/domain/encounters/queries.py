from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .encounter import EncounterState
    from ..creatures import Creature


def active_movement_remaining(state: EncounterState, player: Creature) -> int:
    """Return the movement the player can still spend on the current turn."""
    return state.turn_engine.active_movement_remaining(state, player)
