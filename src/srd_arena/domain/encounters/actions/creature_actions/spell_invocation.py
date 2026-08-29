"""Begin spell actions and open pre-invocation target selection when required."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.spells.rules import SpellActionPayload

from ...encounter_models.actions import EncounterAction
from ...encounter_models.decisions import DecisionFrame, PendingSpellCast
from ...encounter_models.resolution import EncounterProgress
from ...participants import creature_controller
from ..spellcasting import resolve_spell_action
from .spell_invocation_planning import (
    SpellInvocationPlan,
    automatic_spell_payload,
    plan_spell_invocation,
)

if TYPE_CHECKING:
    from srd_arena.domain.creatures import Creature

    from ...encounter import EncounterState


def execute_spell_invocation(
    state: EncounterState,
    actor: Creature,
    action: EncounterAction,
    decision: DecisionFrame,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Resolve a complete cast or suspend it before casting for target choices.

    >>> from types import SimpleNamespace
    >>> execute_spell_invocation(
    ...     SimpleNamespace(), SimpleNamespace(), EncounterAction('Cast', 'spell'),
    ...     DecisionFrame('turn', 'mage', 'turn', 'active'),
    ...     EncounterProgress(), 'cast-1'
    ... )
    Traceback (most recent call last):
    ...
    ValueError: Spell action requires a spell payload.
    """

    if not isinstance(action.value, SpellActionPayload):
        raise ValueError("Spell action requires a spell payload.")
    plan = plan_spell_invocation(state, actor, action.value)
    if (
        plan.staged_selection_needed
        and plan.spell is not None
        and creature_controller(state, decision.creature_ref) != "external"
    ):
        resolve_spell_action(
            state,
            actor,
            automatic_spell_payload(state, actor, action.value, plan),
            progress,
            action_id,
        )
        return
    if plan.staged_selection_needed:
        _open_spell_target_selection(
            state,
            action,
            decision,
            progress,
            action_id,
            plan,
        )
        return
    resolve_spell_action(
        state,
        actor,
        action.value,
        progress,
        action_id,
    )


def _open_spell_target_selection(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
    progress: EncounterProgress,
    action_id: str,
    plan: SpellInvocationPlan,
) -> None:
    """Suspend before invocation and expose the spell's remaining choices."""

    state.interrupts.pending_spell_cast = PendingSpellCast(
        action=action,
        spell_id=plan.spell_id,
        selected_target_refs=list(plan.selected_target_refs),
        maximum_targets=plan.maximum_targets,
        repeat_target_allocations=plan.repeat_target_allocations,
        require_full_target_count=plan.require_full_target_count,
        resource_pool_total=plan.resource_pool_total,
        resource_allocation_limits=dict(plan.resource_allocation_limits),
    )
    state.interrupts.decision_stack.append(
        DecisionFrame(
            id=f"spell-targets-{action_id}",
            creature_ref=decision.creature_ref,
            kind="spell_targets",
            reason=(
                f"Allocate {plan.maximum_targets} spell effects."
                if plan.require_full_target_count
                else f"Choose up to {plan.maximum_targets} spell targets."
            ),
            parent_frame_id=decision.id,
            parent_action_id=action_id,
        )
    )
    progress.paused_for_decision = True
