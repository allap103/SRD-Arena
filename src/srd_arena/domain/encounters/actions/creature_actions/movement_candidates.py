"""Discover legal one-cell movement choices for the acting creature."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...behaviors import DIRECTION_DELTAS
from ...encounter_models.actions import (
    ActionCost,
    CreatureRef,
    EncounterAction,
)

if TYPE_CHECKING:
    from ...encounter import EncounterState


def movement_action_candidates(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> list[EncounterAction]:
    """Build movement candidates that fit the grid and remaining movement budget.

    >>> from types import SimpleNamespace
    >>> from ....geometry import MovementBudget, MovementCost
    >>> actor = SimpleNamespace(movement_remaining=MovementBudget(6))
    >>> state = SimpleNamespace(
    ...     creatures={"hero": actor},
    ...     _movement_cost_for=lambda ref: MovementCost(1),
    ... )
    >>> actions = movement_action_candidates(state, "hero")
    >>> (len(actions), actions[0].kind, actions[0].cost.movement)
    (8, 'move', 1)
    """

    actor = state.creatures[creature_ref]
    movement_cost = state._movement_cost_for(creature_ref)
    if actor.movement_remaining is None:
        actor.movement_remaining = state.combat_rules.movement_budget(
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
