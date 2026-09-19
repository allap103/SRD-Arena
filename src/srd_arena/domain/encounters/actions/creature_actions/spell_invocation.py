"""Resolve complete spell actions and preserve genuine resolution decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.spells.rules import SpellActionPayload

from ...encounter_models.actions import EncounterAction
from ...encounter_models.decisions import (
    DecisionFrame,
    ResumeSpellInvocation,
)
from ...encounter_models.resolution import EncounterProgress
from ...participants import creature_controller
from ..d20_roll_modifiers import (
    open_d20_roll_modifier_decision,
    spell_d20_occurrences,
)
from ..spellcasting import resolve_spell_action
from .spell_invocation_planning import (
    automatic_spell_payload,
    plan_spell_invocation,
)

if TYPE_CHECKING:
    from srd_arena.domain.creatures import Creature
    from srd_arena.domain.spells import Spell

    from ...encounter import EncounterState


def execute_spell_invocation(
    state: EncounterState,
    actor: Creature,
    action: EncounterAction,
    decision: DecisionFrame,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Resolve a complete cast or reject missing configuration.

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
    if action.value.selection_complete:
        resolve_or_offer_spell_d20_choices(
            state,
            actor,
            action.value,
            progress,
            action_id,
            spell=plan.spell,
            target_refs=action.value.target_refs,
        )
        return
    if (
        plan.configuration_needed
        and plan.spell is not None
        and creature_controller(state, decision.creature_ref) != "external"
    ):
        payload = automatic_spell_payload(state, actor, action.value, plan)
        resolve_or_offer_spell_d20_choices(
            state,
            actor,
            payload,
            progress,
            action_id,
            spell=plan.spell,
            target_refs=payload.target_refs,
        )
        return
    if plan.configuration_needed:
        raise ValueError("Provide a complete spell cast before invocation.")
    resolve_or_offer_spell_d20_choices(
        state,
        actor,
        action.value,
        progress,
        action_id,
        spell=plan.spell,
        target_refs=plan.selected_target_refs,
    )


def resolve_or_offer_spell_d20_choices(
    state: EncounterState,
    actor: Creature,
    payload: SpellActionPayload,
    progress: EncounterProgress,
    action_id: str,
    *,
    spell: Spell | None,
    target_refs: tuple[str, ...],
) -> None:
    """Resolve a targeted spell or pause for its optional D20 modifiers."""

    caster_ref = state.current_decision().creature_ref
    if spell is not None and open_d20_roll_modifier_decision(
        state,
        spell_d20_occurrences(state, spell, caster_ref, target_refs),
        action_id=action_id,
        continuation=ResumeSpellInvocation(caster_ref, payload, action_id),
        progress=progress,
    ):
        return
    resolve_spell_action(state, actor, payload, progress, action_id)
