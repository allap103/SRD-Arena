"""Execute movement and suspend it for opportunity-attack decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.geometry import MovementBudget, MovementCost, Position

from ...behaviors import DIRECTION_DELTAS
from ...encounter_models.actions import EncounterAction
from ...encounter_models.decisions import DecisionFrame
from ...encounter_models.resolution import (
    ActionExecutionContext,
    ActionExecutionOutcome,
    ActionExecutionResult,
)
from ...grappling_state import grappling_targets_for, movement_cost_for
from ...reaction_runtime.opportunity_execution import (
    resolve_automatic_opportunity_attacks,
)
from ...reaction_runtime.opportunity_offers import queue_opportunity_attack
from ...state_runtime import create_event

if TYPE_CHECKING:
    from ...encounter import EncounterState


def execute_movement(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
    context: ActionExecutionContext,
) -> ActionExecutionResult | None:
    """Resolve one grid step or return while an interrupt owns the decision.

    When an external Opportunity Attack is offered, movement remains suspended
    and its context is returned to the orchestration layer.

    >>> from types import SimpleNamespace
    >>> mover = SimpleNamespace(
    ...     position=Position(0, 0), movement_remaining=6,
    ...     movement_spent_this_turn=MovementCost(0), is_alive=True,
    ... )
    >>> state = SimpleNamespace(creatures={"hero": mover})
    >>> decision = DecisionFrame("turn", "hero", "turn", "active")
    >>> context = SimpleNamespace(
    ...     actor_ref="hero", progress=SimpleNamespace(paused_for_decision=False),
    ...     action_id="move-1",
    ... )
    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.creature_actions.movement."
    ...     "movement_cost_for", return_value=MovementCost(1)
    ... ), patch(
    ...     "srd_arena.domain.encounters.actions.creature_actions.movement."
    ...     "grappling_targets_for", return_value=()
    ... ), patch(
    ...     "srd_arena.domain.encounters.actions.creature_actions.movement."
    ...     "queue_opportunity_attack", return_value=True
    ... ):
    ...     result = execute_movement(
    ...         state, EncounterAction("Right", "move", "right"), decision, context
    ...     )
    >>> (result.outcome, context.progress.paused_for_decision)
    (<ActionExecutionOutcome.PAUSE_FOR_DECISION: 'pause_for_decision'>, True)
    """

    mover = state.creatures[context.actor_ref]
    progress = context.progress
    action_id = context.action_id
    direction = str(action.value)
    dx, dy = DIRECTION_DELTAS[direction]
    destination = Position(mover.position.x + dx, mover.position.y + dy)
    movement_cost = movement_cost_for(state, decision.creature_ref)
    if movement_cost is None:
        raise RuntimeError("Movement is unavailable for this creature.")
    remaining = MovementBudget(max(0, (mover.movement_remaining or 0) - movement_cost))
    grappled_refs = grappling_targets_for(state, decision.creature_ref)
    grappled_positions = {
        target_ref: Position(
            state.creatures[target_ref].position.x + dx,
            state.creatures[target_ref].position.y + dy,
        )
        for target_ref in grappled_refs
    }
    if queue_opportunity_attack(
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
        resolve_automatic_opportunity_attacks(
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
        create_event(
            state,
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
