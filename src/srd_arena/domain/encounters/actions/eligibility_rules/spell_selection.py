"""Validate staged spell target, allocation, and confirmation actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ....spells.definitions import Spell
from ....spells.rules import parse_spell_action_value, spell_chooses_area_targets
from ...encounter_models.actions import CreatureRef, EncounterAction
from ...encounter_models.decisions import PendingSpellCast
from ..option_discovery.spell_areas import spell_area_targets
from ..option_discovery.spell_targets import spell_action_targets
from .common import target_requirement_failure
from .models import EligibilityFailure

if TYPE_CHECKING:
    from ....creatures import Creature
    from ...encounter import EncounterState


@dataclass(frozen=True)
class StagedSpellSelection:
    """Hold the pending casting and currently eligible target references."""

    pending: PendingSpellCast
    spell: Spell
    candidate_refs: frozenset[str]


def check_staged_spell_selection(
    state: EncounterState,
    actor_ref: CreatureRef,
    action: EncounterAction,
) -> EligibilityFailure | None:
    """Dispatch one staged spell action to its focused eligibility check.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(
    ...     interrupts=SimpleNamespace(pending_spell_cast=None)
    ... )
    >>> action = EncounterAction("Confirm", "confirm_spell_targets")
    >>> check_staged_spell_selection(state, "hero", action).code
    'spell_selection_unavailable'
    """

    selection = _resolve_staged_selection(state, actor_ref)
    if isinstance(selection, EligibilityFailure):
        return selection
    if action.kind == "toggle_spell_target":
        return _check_target_toggle(state, actor_ref, action, selection)
    if action.kind == "set_spell_resource_allocation":
        return _check_resource_allocation(state, actor_ref, action, selection)
    if action.kind == "confirm_spell_targets":
        return _check_confirmation(state, actor_ref, selection)
    return None


def _resolve_staged_selection(
    state: EncounterState,
    actor_ref: CreatureRef,
) -> StagedSpellSelection | EligibilityFailure:
    """Resolve the pending spell and recompute its currently eligible targets."""

    pending = state.interrupts.pending_spell_cast
    if pending is None:
        return EligibilityFailure(
            "spell_selection_unavailable",
            "No spell target selection is active.",
        )
    actor = state.creatures[actor_ref].creature
    spell = _known_spell(actor, pending.spell_id)
    if spell is None:
        return EligibilityFailure(
            "spell_unavailable",
            "The staged spell is no longer available.",
        )
    _spell_id, _target, aim_point = parse_spell_action_value(str(pending.action.value))
    candidates = (
        spell_area_targets(state, actor, spell, aim_point=aim_point)
        if spell_chooses_area_targets(spell)
        else tuple(spell_action_targets(state, actor, spell))
    )
    return StagedSpellSelection(
        pending=pending,
        spell=spell,
        candidate_refs=frozenset(target.target_ref for target in candidates),
    )


def _known_spell(actor: Creature, spell_id: str) -> Spell | None:
    """Return the actor's currently known spell with the requested ID."""

    if actor.spellcasting is None:
        return None
    return next(
        (spell for spell in actor.spellcasting.learned_spells if spell.id == spell_id),
        None,
    )


def _check_target_toggle(
    state: EncounterState,
    actor_ref: CreatureRef,
    action: EncounterAction,
    selection: StagedSpellSelection,
) -> EligibilityFailure | None:
    """Validate adding or removing one target allocation."""

    pending = selection.pending
    if not isinstance(action.value, str):
        return EligibilityFailure(
            "target_required",
            "A creature target is required.",
        )
    if action.id.endswith("-remove"):
        if action.value not in pending.selected_target_refs:
            return EligibilityFailure(
                "target_unavailable",
                "That target has no allocated spell effect to remove.",
            )
        return None
    if (
        not pending.repeat_target_allocations
        and action.value in pending.selected_target_refs
    ):
        return None
    if len(pending.selected_target_refs) >= pending.maximum_targets:
        return EligibilityFailure(
            "target_limit_reached",
            "The spell's target limit has been reached.",
        )
    if action.value not in selection.candidate_refs:
        return EligibilityFailure(
            "target_unavailable",
            "The target is not available for this spell.",
        )
    return target_requirement_failure(
        state,
        actor_ref,
        action.value,
        selection.spell.target_requirements,
    )


def _check_resource_allocation(
    state: EncounterState,
    actor_ref: CreatureRef,
    action: EncounterAction,
    selection: StagedSpellSelection,
) -> EligibilityFailure | None:
    """Validate one target's requested share of a spell resource pool."""

    pending = selection.pending
    if pending.resource_pool_total is None or not isinstance(action.value, str):
        return EligibilityFailure(
            "spell_allocation_unavailable",
            "No spell resource allocation is active.",
        )
    target_ref, separator, amount_text = action.value.rpartition("~")
    if not separator or not amount_text.isdigit():
        return EligibilityFailure(
            "invalid_allocation",
            "The allocation must provide a target and whole-number amount.",
        )
    amount = int(amount_text)
    limit = pending.resource_allocation_limits.get(target_ref)
    other_total = sum(
        value
        for ref, value in pending.resource_allocations.items()
        if ref != target_ref
    )
    if limit is None or amount > limit:
        return EligibilityFailure(
            "invalid_allocation",
            "The allocation exceeds that target's missing Hit Points.",
        )
    if other_total + amount > pending.resource_pool_total:
        return EligibilityFailure(
            "resource_pool_exceeded",
            "The allocation exceeds the remaining healing pool.",
        )
    return target_requirement_failure(
        state,
        actor_ref,
        target_ref,
        selection.spell.target_requirements,
    )


def _check_confirmation(
    state: EncounterState,
    actor_ref: CreatureRef,
    selection: StagedSpellSelection,
) -> EligibilityFailure | None:
    """Validate the complete selected-target or resource allocation."""

    pending = selection.pending
    if pending.resource_pool_total is not None:
        if not pending.resource_allocations:
            return EligibilityFailure(
                "target_required",
                "Allocate at least 1 Hit Point before casting.",
            )
        return None
    if not pending.selected_target_refs:
        return EligibilityFailure(
            "target_required",
            "Select at least one spell target.",
        )
    if (
        pending.require_full_target_count
        and len(pending.selected_target_refs) != pending.maximum_targets
    ):
        return EligibilityFailure(
            "target_allocation_incomplete",
            "Allocate every spell effect before casting.",
        )
    for target_ref in pending.selected_target_refs:
        if target_ref not in selection.candidate_refs:
            return EligibilityFailure(
                "target_unavailable",
                "A selected target is no longer available for this spell.",
            )
        failure = target_requirement_failure(
            state,
            actor_ref,
            target_ref,
            selection.spell.target_requirements,
        )
        if failure is not None:
            return failure
    return None
