"""Expose read-only encounter queries used by orchestration and clients."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..geometry import MovementBudget

if TYPE_CHECKING:
    from .encounter import EncounterState


def active_movement_remaining(state: EncounterState) -> MovementBudget:
    """Return the movement the current decision actor can still spend.

    >>> from types import SimpleNamespace
    >>> lifecycle = SimpleNamespace(
    ...     active_movement_remaining=lambda state: MovementBudget(5)
    ... )
    >>> active_movement_remaining(SimpleNamespace(turn_lifecycle=lifecycle))
    5
    """
    return state.turn_lifecycle.active_movement_remaining(state)
