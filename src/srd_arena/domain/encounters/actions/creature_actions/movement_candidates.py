from __future__ import annotations

from typing import TYPE_CHECKING

from ...behaviors import DIRECTION_DELTAS, movement_budget_for
from ...models import ActionCost, CreatureRef, EncounterAction

if TYPE_CHECKING:
    from ...encounter import EncounterState


def movement_action_candidates(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> list[EncounterAction]:
    actor = state.creatures[creature_ref]
    movement_cost = state._movement_cost_for(creature_ref)
    if actor.movement_remaining is None:
        actor.movement_remaining = movement_budget_for(
            actor.creature,
            state.definition.grid,
        )
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
