"""Open and classify one creature action execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.spells.action_payloads import (
    SpellActionPayload,
    serialize_spell_action_payload,
)

from ...encounter_models.actions import EncounterAction
from ...encounter_models.decisions import DecisionFrame
from ...encounter_models.resolution import (
    ActionExecutionContext,
    ActionExecutionOutcome,
    ActionExecutionResult,
)
from ...state_runtime import create_event, next_action_id
from ..eligibility import action_eligibility
from ..rejections import reject_action

if TYPE_CHECKING:
    from ...encounter import EncounterState


def begin_action_execution(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> ActionExecutionContext:
    """Validate and record the declaration of a selected action."""

    eligibility = action_eligibility(
        state,
        decision.creature_ref,
        action,
    )
    actor = state.creatures[decision.creature_ref]
    context = ActionExecutionContext(
        actor_ref=decision.creature_ref,
        actor=actor,
        decision=decision,
        action=action,
        action_id=next_action_id(state),
    )
    event_value = (
        serialize_spell_action_payload(action.value)
        if isinstance(action.value, SpellActionPayload)
        else action.value
    )
    context.progress.events.append(
        create_event(
            state,
            "action_declared",
            creature_ref=context.actor_ref,
            action_id=context.action_id,
            data={
                "kind": action.kind,
                "value": event_value,
                "selected_action_id": action.id,
            },
        )
    )
    if eligibility.failures:
        failure = eligibility.failures[0]
        context.rejection = reject_action(
            state,
            context.progress,
            actor_ref=context.actor_ref,
            action_id=context.action_id,
            action_kind=action.kind,
            message=failure.message,
            reason_code=failure.code,
            details={
                "selected_action_id": action.id,
                "action_value": event_value,
                "failure_codes": [item.code for item in eligibility.failures],
                "provider_state_ids": [
                    state_id
                    for item in eligibility.failures
                    for state_id in item.state_ids
                ],
            },
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

    if context.progress.completed:
        outcome = ActionExecutionOutcome.ENCOUNTER_COMPLETE
    elif context.progress.paused_for_decision:
        outcome = ActionExecutionOutcome.PAUSE_FOR_DECISION
    elif action_ends_turn:
        outcome = ActionExecutionOutcome.END_TURN
    else:
        outcome = ActionExecutionOutcome.CONTINUE_TURN
    return ActionExecutionResult(context, outcome)
