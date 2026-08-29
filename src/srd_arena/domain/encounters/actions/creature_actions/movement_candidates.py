"""Discover legal one-cell movement choices for the acting creature."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...behaviors import DIRECTION_DELTAS
from ...encounter_models.actions import (
    ActionCost,
    CreatureRef,
    EncounterAction,
)
from ...grappling_state import movement_cost_for
from ...rule_queries.numeric import movement_budget

if TYPE_CHECKING:
    from ...encounter import EncounterState


def movement_action_candidates(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> list[EncounterAction]:
    """Build movement candidates that fit the grid and remaining movement budget.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.geometry import MovementBudget, MovementCost
    >>> actor = SimpleNamespace(movement_remaining=MovementBudget(6))
    >>> state = SimpleNamespace(creatures={"hero": actor})
    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.creature_actions."
    ...     "movement_candidates.movement_cost_for",
    ...     return_value=MovementCost(1),
    ... ):
    ...     actions = movement_action_candidates(state, "hero")
    >>> (len(actions), actions[0].kind, actions[0].cost.movement)
    (8, 'move', 1)
    """

    actor = state.creatures[creature_ref]
    movement_cost = movement_cost_for(state, creature_ref)
    if actor.movement_remaining is None:
        actor.movement_remaining = movement_budget(
            state,
            creature_ref,
        ).budget
    if movement_cost is None:
        return []
    return [
        EncounterAction(
            f"Move {direction}",
            "move",
            direction,
            id=f"{creature_ref}-move-{direction}",
            creature_ref=creature_ref,
            cost=ActionCost(movement=movement_cost),
        )
        for direction in DIRECTION_DELTAS
    ]
