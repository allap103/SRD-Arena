"""Mutate and complete a staged pre-invocation spell-target decision."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from srd_arena.domain.spells.rules import (
    SpellActionPayload,
)

from ...encounter_models.actions import EncounterAction
from ...encounter_models.resolution import EncounterProgress
from ..spellcasting import resolve_spell_action

if TYPE_CHECKING:
    from srd_arena.domain.creatures import Creature

    from ...encounter import EncounterState


def execute_spell_selection_action(
    state: EncounterState,
    actor: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> bool:
    """Apply one command to the active staged spell selection.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(
    ...     interrupts=SimpleNamespace(
    ...         pending_spell_cast=object(), decision_stack=[object()]
    ...     )
    ... )
    >>> execute_spell_selection_action(
    ...     state, SimpleNamespace(),
    ...     EncounterAction("Cancel", "cancel_spell_targets"),
    ...     EncounterProgress(), "cancel-1"
    ... )
    True
    >>> (state.interrupts.pending_spell_cast, state.interrupts.decision_stack)
    (None, [])
    >>> execute_spell_selection_action(
    ...     state, SimpleNamespace(), EncounterAction("Wait", "wait"),
    ...     EncounterProgress(), "wait-1"
    ... )
    False
    """

    if action.kind == "toggle_spell_target":
        _toggle_spell_target(state, action, progress)
    elif action.kind == "set_spell_resource_allocation":
        _set_spell_resource_allocation(state, action, progress)
    elif action.kind == "confirm_spell_targets":
        _confirm_spell_targets(state, actor, progress, action_id)
    elif action.kind == "cancel_spell_targets":
        _cancel_spell_targets(state)
    else:
        return False
    return True


def _toggle_spell_target(
    state: EncounterState,
    action: EncounterAction,
    progress: EncounterProgress,
) -> None:
    pending = state.interrupts.pending_spell_cast
    if pending is None or not isinstance(action.value, str):
        raise RuntimeError("No staged spell target selection is active.")
    remove_target = action.id.endswith("-remove")
    if pending.repeat_target_allocations:
        if remove_target and action.value in pending.selected_target_refs:
            pending.selected_target_refs.remove(action.value)
        elif (
            not remove_target
            and len(pending.selected_target_refs) < pending.maximum_targets
        ):
            pending.selected_target_refs.append(action.value)
    elif action.value in pending.selected_target_refs:
        pending.selected_target_refs.remove(action.value)
    elif len(pending.selected_target_refs) < pending.maximum_targets:
        pending.selected_target_refs.append(action.value)
    progress.paused_for_decision = True


def _set_spell_resource_allocation(
    state: EncounterState,
    action: EncounterAction,
    progress: EncounterProgress,
) -> None:
    pending = state.interrupts.pending_spell_cast
    if pending is None or pending.resource_pool_total is None:
        raise RuntimeError("No staged spell resource allocation is active.")
    if not isinstance(action.value, str):
        raise ValueError("Spell resource allocation requires target and amount.")
    target_ref, separator, amount_text = action.value.rpartition("~")
    if not separator or not amount_text.isdigit():
        raise ValueError("Invalid spell resource allocation.")
    amount = int(amount_text)
    target_allocation_limit = pending.resource_allocation_limits.get(target_ref)
    other_total = sum(
        value
        for ref, value in pending.resource_allocations.items()
        if ref != target_ref
    )
    if (
        target_allocation_limit is None
        or amount < 0
        or amount > target_allocation_limit
    ):
        raise ValueError("The allocation exceeds the target's legal amount.")
    if other_total + amount > pending.resource_pool_total:
        raise ValueError("The allocation exceeds the remaining resource pool.")
    if amount:
        pending.resource_allocations[target_ref] = amount
    else:
        pending.resource_allocations.pop(target_ref, None)
    progress.paused_for_decision = True


def _confirm_spell_targets(
    state: EncounterState,
    actor: Creature,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    pending = state.interrupts.pending_spell_cast
    if pending is None or (
        not pending.selected_target_refs and not pending.resource_allocations
    ):
        raise RuntimeError("No staged spell targets can be confirmed.")
    if (
        pending.require_full_target_count
        and len(pending.selected_target_refs) != pending.maximum_targets
    ):
        raise RuntimeError("All spell effects must be allocated before casting.")
    original_payload = pending.action.value
    if not isinstance(original_payload, SpellActionPayload):
        raise TypeError("Staged spell action has no spell payload.")
    resolved_target_refs = (
        tuple(pending.resource_allocations)
        if pending.resource_pool_total is not None
        else tuple(pending.selected_target_refs)
    )
    payload = replace(
        original_payload,
        target_refs=resolved_target_refs,
        healing_allocations=tuple(sorted(pending.resource_allocations.items())),
    )
    state.interrupts.decision_stack.pop()
    state.interrupts.pending_spell_cast = None
    resolve_spell_action(
        state,
        actor,
        payload,
        progress,
        action_id,
    )


def _cancel_spell_targets(state: EncounterState) -> None:
    if state.interrupts.pending_spell_cast is None:
        raise RuntimeError("No staged spell targets can be cancelled.")
    state.interrupts.decision_stack.pop()
    state.interrupts.pending_spell_cast = None
