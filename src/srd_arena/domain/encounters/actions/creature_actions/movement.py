"""Execute movement and suspend it for opportunity-attack decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....geometry import MovementBudget, MovementCost, Position
from ...behaviors import DIRECTION_DELTAS
from ...models import (
    ActionExecutionContext,
    ActionExecutionOutcome,
    ActionExecutionResult,
    DecisionFrame,
    EncounterAction,
)

if TYPE_CHECKING:
    from ...encounter import EncounterState


def execute_movement(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
    context: ActionExecutionContext,
) -> ActionExecutionResult | None:
    """Resolve one grid step or return while an interrupt owns the decision."""

    mover = state.creatures[context.actor_ref]
    progress = context.progress
    action_id = context.action_id
    direction = str(action.value)
    dx, dy = DIRECTION_DELTAS[direction]
    destination = Position(mover.position.x + dx, mover.position.y + dy)
    movement_cost = state._movement_cost_for(decision.creature_ref)
    if movement_cost is None:
        raise RuntimeError("Movement is unavailable for this creature.")
    remaining = MovementBudget(max(0, (mover.movement_remaining or 0) - movement_cost))
    grappled_refs = state._grappling_targets_for(decision.creature_ref)
    grappled_positions = {
        target_ref: Position(
            state.creatures[target_ref].position.x + dx,
            state.creatures[target_ref].position.y + dy,
        )
        for target_ref in grappled_refs
    }
    if state.reaction_engine.queue_opportunity_attack(
        state,
        mover_ref=decision.creature_ref,
        action_id=action_id,
        direction=direction,
        from_position=Position(mover.position.x, mover.position.y),
        to_position=destination,
        remaining_movement_after=remaining,
        movement_cost=movement_cost,
        companion_destinations=grappled_positions,
        progress=progress,
        external_only=True,
        excluded_reactor_refs=grappled_refs,
    ):
        progress.paused_for_decision = True
        return ActionExecutionResult(
            context,
            ActionExecutionOutcome.PAUSE_FOR_DECISION,
        )
    progress.messages.extend(
        state.reaction_engine.resolve_automatic_opportunity_attacks(
            state,
            mover_ref=decision.creature_ref,
            from_position=Position(mover.position.x, mover.position.y),
            to_position=destination,
            action_id=action_id,
            progress=progress,
            excluded_reactor_refs=grappled_refs,
        )
    )
    if not mover.is_alive:
        return ActionExecutionResult(
            context,
            ActionExecutionOutcome.CONTINUE_TURN,
        )
    mover.position = destination
    for target_ref, target_position in grappled_positions.items():
        state.creatures[target_ref].position = target_position
    mover.movement_remaining = remaining
    mover.movement_spent_this_turn = MovementCost(
        int(mover.movement_spent_this_turn) + int(movement_cost)
    )
    progress.messages.append(
        (
            "system",
            f"{mover.creature.name} moves {direction} to "
            f"({destination.x}, {destination.y}).",
        )
    )
    progress.events.append(
        state._event(
            "movement_resolved",
            creature_ref=decision.creature_ref,
            action_id=action_id,
            data={
                "direction": direction,
                "to": {"x": destination.x, "y": destination.y},
            },
        )
    )
    return None
