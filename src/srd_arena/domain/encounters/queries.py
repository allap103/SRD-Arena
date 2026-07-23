from __future__ import annotations

from typing import TYPE_CHECKING

from .models import EncounterCreatureState

if TYPE_CHECKING:
    from .encounter import EncounterState
    from ..creatures import Creature


def active_movement_remaining(state: EncounterState, player: Creature) -> int:
    """Return the movement the player can still spend on the current turn."""
    return state.turn_engine.active_movement_remaining(state, player)


def living_non_primary_creature_at(
    state: EncounterState,
    x: int,
    y: int,
) -> EncounterCreatureState | None:
    """Return a living non-primary creature occupying a grid cell."""
    return state.turn_engine.living_non_primary_creature_at(state, x, y)
