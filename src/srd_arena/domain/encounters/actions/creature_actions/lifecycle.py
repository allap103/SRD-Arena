"""Open and classify one creature action execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...models import (
    ActionExecutionContext,
    ActionExecutionOutcome,
    ActionExecutionResult,
    DecisionFrame,
    EncounterAction,
)
from ..eligibility import require_action_eligible

if TYPE_CHECKING:
    from ...encounter import EncounterState


def begin_action_execution(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> ActionExecutionContext:
    """Validate and record the declaration of a selected action."""

    require_action_eligible(state, decision.creature_ref, action)
    actor = state.creatures[decision.creature_ref]
    context = ActionExecutionContext(
        actor_ref=decision.creature_ref,
        actor=actor,
        decision=decision,
        action=action,
        action_id=state._next_action_id(),
    )
    context.progress.events.append(
        state._event(
            "action_declared",
            creature_ref=context.actor_ref,
            action_id=context.action_id,
            data={
                "kind": action.kind,
                "value": action.value,
                "selected_action_id": action.id,
            },
        )
    )
    return context


def finish_action_execution(
    context: ActionExecutionContext,
    *,
    action_ends_turn: bool,
) -> ActionExecutionResult:
    """Translate accumulated progress into the orchestrator's action outcome."""

    if context.progress.transition is not None:
        outcome = ActionExecutionOutcome.ENCOUNTER_COMPLETE
    elif context.progress.paused_for_decision:
        outcome = ActionExecutionOutcome.PAUSE_FOR_DECISION
    elif action_ends_turn:
        outcome = ActionExecutionOutcome.END_TURN
    else:
        outcome = ActionExecutionOutcome.CONTINUE_TURN
    return ActionExecutionResult(context, outcome)

