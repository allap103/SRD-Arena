from __future__ import annotations

from typing import TYPE_CHECKING

from ..geometry import MovementBudget

if TYPE_CHECKING:
    from .encounter import EncounterState


def active_movement_remaining(state: EncounterState) -> MovementBudget:
    """Return the movement the current decision actor can still spend."""
    return state.turn_engine.active_movement_remaining(state)
