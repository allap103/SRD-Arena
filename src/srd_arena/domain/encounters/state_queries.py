"""Read-only queries exposed by :class:`EncounterState`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..effects.condition_rules import EffectiveConditionSet
from ..effects.conditions import AppliedCondition, Condition
from .actions.eligibility import ActionEligibility
from .models import CreatureRef, DecisionFrame, EncounterAction

if TYPE_CHECKING:
    from .encounter import EncounterState


def current_turn_label(state: EncounterState) -> str:
    """Handle current turn label."""

    decision = state.current_decision()
    if decision.kind == "reaction":
        return f"{state._creature_label(decision.creature_ref)} (Reaction)"
    return state._creature_label(decision.creature_ref)


def current_decision(state: EncounterState) -> DecisionFrame:
    """Handle current decision."""

    if state.decision_stack:
        return state.decision_stack[-1]
    creature_ref = state.turn_lifecycle.active_turn_creature(state)
    return DecisionFrame(
        id=f"turn-{creature_ref.replace(':', '-')}",
        creature_ref=creature_ref,
        kind="turn",
        reason="normal_turn",
    )


def conditions_for(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> tuple[AppliedCondition, ...]:
    """Handle conditions for."""

    return tuple(
        condition
        for condition in state.conditions
        if condition.target_ref == creature_ref
    )


def has_condition(
    state: EncounterState,
    creature_ref: CreatureRef,
    condition: Condition,
) -> bool:
    """Return whether condition."""

    return any(
        applied.condition is condition for applied in state.conditions_for(creature_ref)
    )


def effective_conditions_for(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> EffectiveConditionSet:
    """Handle effective conditions for."""

    return state.combat_rules.effective_conditions(state, creature_ref)


def active_creature(state: EncounterState) -> CreatureRef:
    """Handle active creature."""

    return state.current_decision().creature_ref


def requires_automatic_advance(state: EncounterState) -> bool:
    """Handle requires automatic advance."""

    return (
        state._creature_controller(state.current_decision().creature_ref) == "scripted"
    )


def action_eligibility(
    state: EncounterState,
    action: EncounterAction,
) -> ActionEligibility:
    """Handle action eligibility."""

    return state.combat_rules.action_eligibility(
        state,
        state.current_decision().creature_ref,
        action,
    )
