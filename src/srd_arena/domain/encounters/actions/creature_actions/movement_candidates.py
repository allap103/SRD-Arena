"""Discover legal one-cell movement choices for the acting creature."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.geometry import Position

from ...behaviors import DIRECTION_DELTAS
from ...encounter_models.actions import (
    ActionCost,
    CreatureRef,
    EncounterAction,
)
from ...grappling_state import is_grappled
from ...rule_queries.movement import movement_step_cost
from ...rule_queries.numeric import movement_budget
from ...spatial import creature_position

if TYPE_CHECKING:
    from ...encounter import EncounterState


def movement_action_candidates(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> list[EncounterAction]:
    """Build movement candidates that fit the grid and remaining movement budget.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.geometry import MovementBudget, MovementCost
    >>> actor = SimpleNamespace(
    ...     movement_remaining=MovementBudget(6), position=Position(1, 1)
    ... )
    >>> state = SimpleNamespace(creatures={"hero": actor}, conditions=[])
    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.creature_actions."
    ...     "movement_candidates.movement_step_cost",
    ...     return_value=MovementCost(1),
    ... ):
    ...     actions = movement_action_candidates(state, "hero")
    >>> (len(actions), actions[0].kind, actions[0].cost.movement)
    (8, 'move', 1)
    """

    actor = state.creatures[creature_ref]
    if actor.movement_remaining is None:
        actor.movement_remaining = movement_budget(
            state,
            creature_ref,
        ).budget
    if is_grappled(state, creature_ref):
        return []
    actions: list[EncounterAction] = []
    source = creature_position(state, creature_ref)
    for direction, (dx, dy) in DIRECTION_DELTAS.items():
        destination = Position(source.x + dx, source.y + dy)
        actions.append(
            EncounterAction(
                f"Move {direction}",
                "move",
                direction,
                id=f"{creature_ref}-move-{direction}",
                creature_ref=creature_ref,
                cost=ActionCost(
                    movement=movement_step_cost(state, creature_ref, destination)
                ),
            )
        )
    return actions
