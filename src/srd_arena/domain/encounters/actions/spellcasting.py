"""Coordinate encounter spell execution.

This stable entry point keeps cast preparation readable while delegating
source-neutral context construction and encounter aftermath to focused
spell-runtime helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature
from ...spells.resolution import resolve_spell_action as _resolve_spell_action_impl
from ...spells.rules import (
    parse_spell_action_slot,
    parse_spell_action_targets,
    parse_spell_action_value,
)
from ..encounter_models.resolution import EncounterProgress
from .spell_runtime.aftermath import apply_spell_result
from .spell_runtime.context import build_spell_action_context
from .spell_runtime.invocation import begin_spell_invocation

if TYPE_CHECKING:
    from ..encounter import EncounterState


def _roll_die(sides: int) -> int:
    """Roll through the encounter module's runtime-patchable dice seam."""

    from .. import encounter as encounter_module

    return encounter_module.roll_die(sides)


def resolve_spell_action(
    state: EncounterState,
    actor: Creature,
    spell_value: str,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Prepare, resolve, and apply one selected spell action.

    >>> from types import SimpleNamespace
    >>> actor = SimpleNamespace(spellcasting=None)
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="fighter"),
    ...     _event=lambda event_type, **values: (event_type, values["data"]),
    ... )
    >>> progress = EncounterProgress()
    >>> resolve_spell_action(state, actor, "fireball", progress, "cast-1")
    >>> (progress.messages[-1], progress.events[-1][1]["success"])
    (('system', 'You cannot cast spells.'), False)
    """

    creature_ref = state.current_decision().creature_ref
    spellcasting = actor.spellcasting
    if spellcasting is None:
        _record_failed_spell_action(
            state,
            progress,
            creature_ref=creature_ref,
            action_id=action_id,
            message="You cannot cast spells.",
        )
        return

    spell_id, target_ref, aim_point = parse_spell_action_value(spell_value)
    selected_target_refs = parse_spell_action_targets(spell_value)
    cast_level = parse_spell_action_slot(spell_value)
    spell = next(
        (
            candidate
            for candidate in spellcasting.learned_spells
            if candidate.id == spell_id
        ),
        None,
    )
    if spell is None:
        _record_failed_spell_action(
            state,
            progress,
            creature_ref=creature_ref,
            action_id=action_id,
            message="That spell is not available.",
            spell_id=spell_id,
        )
        return

    cost = state._spell_action_cost(spell)
    block_reason: str | None
    if cast_level is not None and (
        spell.level == 0 or cast_level <= spell.level or cast_level > 9
    ):
        block_reason = "That spell slot level is not available for this spell."
    else:
        block_reason = state._spell_cast_block_reason(
            spellcasting,
            spell,
            cost,
            cast_level,
        )
    if block_reason is not None:
        _record_failed_spell_action(
            state,
            progress,
            creature_ref=creature_ref,
            action_id=action_id,
            message=block_reason,
            spell_id=spell.id,
        )
        return

    area = state._spell_area(
        actor,
        spell,
        target_ref=target_ref,
        aim_point=aim_point,
    )
    targets = (
        tuple(
            target
            for selected_ref in selected_target_refs
            if (target := state._spell_target_context(actor, selected_ref)) is not None
        )
        if selected_target_refs
        else state._spell_area_targets(
            actor,
            spell,
            target_ref=target_ref,
            aim_point=aim_point,
        )
    )
    target = targets[0] if targets else None
    if target is None or not targets:
        _record_failed_spell_action(
            state,
            progress,
            creature_ref=creature_ref,
            action_id=action_id,
            message="That target is not available.",
            spell_id=spell.id,
        )
        return

    if spell.definition is None:
        _record_failed_spell_action(
            state,
            progress,
            creature_ref=creature_ref,
            action_id=action_id,
            message=f"{spell.name} is not implemented yet.",
            spell_id=spell.id,
        )
        return

    if not begin_spell_invocation(
        state,
        actor=actor,
        spellcasting=spellcasting,
        spell=spell,
        cost=cost,
        cast_level=cast_level,
        creature_ref=creature_ref,
        action_id=action_id,
        progress=progress,
    ):
        return

    result = _resolve_spell_action_impl(
        build_spell_action_context(
            state,
            actor=actor,
            spell=spell,
            spell_value=spell_value,
            creature_ref=creature_ref,
            target=target,
            targets=targets,
            area=area,
            cast_level=cast_level,
        )
    )
    if result is None:
        _record_failed_spell_action(
            state,
            progress,
            creature_ref=creature_ref,
            action_id=action_id,
            message=f"{spell.name} is not implemented yet.",
            spell_id=spell.id,
        )
        return

    apply_spell_result(
        state,
        spellcasting=spellcasting,
        spell=spell,
        cast_level=cast_level,
        creature_ref=creature_ref,
        action_id=action_id,
        result=result,
        progress=progress,
        target_ref=target_ref,
        target=target,
    )


def _record_failed_spell_action(
    state: EncounterState,
    progress: EncounterProgress,
    *,
    creature_ref: str,
    action_id: str,
    message: str,
    spell_id: str | None = None,
) -> None:
    """Record a cast rejected before source-neutral resolution begins."""

    progress.messages.append(("system", message))
    data: dict[str, object] = {"kind": "spell"}
    if spell_id is not None:
        data["spell_id"] = spell_id
    data["success"] = False
    progress.events.append(
        state._event(
            "action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data=data,
        )
    )


__all__ = ["_roll_die", "resolve_spell_action"]
