from __future__ import annotations

from typing import TYPE_CHECKING

from .models import EncounterEnemyState

if TYPE_CHECKING:
    from .encounter import EncounterState
    from ..creature import Creature


def player_movement_remaining(state: EncounterState, player: Creature) -> int:
    """Return the movement the player can still spend on the current turn."""
    return state.turn_engine.player_movement_remaining(state, player)


def living_enemy_at(state: EncounterState, x: int, y: int) -> EncounterEnemyState | None:
    """Return the living enemy occupying a grid cell, if any."""
    return state.turn_engine.live_enemy_at(state, x, y)
