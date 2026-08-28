"""Open and classify one creature action execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...encounter_models.actions import EncounterAction
from ...encounter_models.decisions import DecisionFrame
from ...encounter_models.resolution import (
    ActionExecutionContext,
    ActionExecutionOutcome,
    ActionExecutionResult,
)
from ...state_runtime import create_event, next_action_id
from ..eligibility import require_action_eligible

if TYPE_CHECKING:
    from ...encounter import EncounterState


def begin_action_execution(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> ActionExecutionContext:
    """Validate and record the declaration of a selected action.

    >>> from types import SimpleNamespace
    >>> from ..eligibility_rules.models import ActionEligibility
    >>> decision = DecisionFrame("turn-hero", "hero", "turn", "normal_turn")
    >>> state = SimpleNamespace(
    ...     creatures={"hero": object()},
    ...     combat_rules=SimpleNamespace(
    ...         action_eligibility=lambda *args: ActionEligibility()
    ...     ),
    ...     action_sequence=1, event_sequence=1,
    ... )
    >>> context = begin_action_execution(
    ...     state, EncounterAction("Wait", "wait"), decision
    ... )
    >>> (context.action_id, context.progress.events[0].type)
    ('action_1', 'action_declared')
    """

    require_action_eligible(state, decision.creature_ref, action)
    actor = state.creatures[decision.creature_ref]
    context = ActionExecutionContext(
        actor_ref=decision.creature_ref,
        actor=actor,
        decision=decision,
        action=action,
        action_id=next_action_id(state),
    )
    context.progress.events.append(
        create_event(
            state,
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
    """Translate accumulated progress into the orchestrator's action outcome.

    >>> from types import SimpleNamespace
    >>> from ...encounter_models.resolution import EncounterProgress
    >>> context = SimpleNamespace(progress=EncounterProgress())
    >>> finish_action_execution(context, action_ends_turn=True).outcome.value
    'end_turn'
    """

    if context.progress.transition is not None:
        outcome = ActionExecutionOutcome.ENCOUNTER_COMPLETE
    elif context.progress.paused_for_decision:
        outcome = ActionExecutionOutcome.PAUSE_FOR_DECISION
    elif action_ends_turn:
        outcome = ActionExecutionOutcome.END_TURN
    else:
        outcome = ActionExecutionOutcome.CONTINUE_TURN
    return ActionExecutionResult(context, outcome)
