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
    """Return the display label of the creature whose turn is active."""

    decision = state.current_decision()
    if decision.kind == "reaction":
        return f"{state._creature_label(decision.creature_ref)} (Reaction)"
    return state._creature_label(decision.creature_ref)


def current_decision(state: EncounterState) -> DecisionFrame:
    """Return the unresolved decision at the top of the encounter stack."""

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
    """Return stored condition applications for a creature, including suppressed ones."""

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
    """Return whether the condition's mechanics currently affect the creature."""

    return any(
        applied.condition is condition for applied in state.conditions_for(creature_ref)
    )


def effective_conditions_for(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> EffectiveConditionSet:
    """Return condition kinds whose mechanics currently apply to a creature."""

    return state.combat_rules.effective_conditions(state, creature_ref)


def active_creature(state: EncounterState) -> CreatureRef:
    """Return the creature owning the current initiative turn."""

    return state.current_decision().creature_ref


def requires_automatic_advance(state: EncounterState) -> bool:
    """Return whether the current decision belongs to an automatic controller."""

    return (
        state._creature_controller(state.current_decision().creature_ref) == "scripted"
    )


def action_eligibility(
    state: EncounterState,
    action: EncounterAction,
) -> ActionEligibility:
    """Evaluate a candidate action against the encounter's eligibility rules."""

    return state.combat_rules.action_eligibility(
        state,
        state.current_decision().creature_ref,
        action,
    )
