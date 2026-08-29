"""Coordinate encounter spell execution.

This stable entry point keeps cast preparation readable while delegating
source-neutral context construction and encounter aftermath to focused
spell-runtime helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures import Creature
from srd_arena.domain.spells.resolution import (
    resolve_spell_action as _resolve_spell_action_impl,
)
from srd_arena.domain.spells.rules import SpellActionPayload

from ..encounter_models.resolution import EncounterProgress
from .option_discovery.spell_areas import spell_area, spell_area_targets
from .option_discovery.spell_targets import spell_target_context
from .option_discovery.spellcasting import (
    spell_action_cost,
    spell_cast_block_reason_for,
)
from .rejections import reject_action
from .spell_runtime.aftermath import apply_spell_result
from .spell_runtime.context import build_spell_action_context
from .spell_runtime.invocation import begin_spell_invocation

if TYPE_CHECKING:
    from ..encounter import EncounterState


def resolve_spell_action(
    state: EncounterState,
    actor: Creature,
    payload: SpellActionPayload,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Prepare, resolve, and apply one selected spell action.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.spells.rules import spell_action_payload
    >>> actor = SimpleNamespace(spellcasting=None)
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="fighter"),
    ...     event_sequence=1,
    ... )
    >>> progress = EncounterProgress()
    >>> resolve_spell_action(
    ...     state, actor, spell_action_payload("fireball"), progress, "cast-1"
    ... )
    >>> (progress.messages[-1], progress.events[-1].data["reason_code"])
    (('system', 'You cannot cast spells.'), 'spellcasting_unavailable')
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
            reason_code="spellcasting_unavailable",
        )
        return

    spell_id = payload.spell_id
    target_ref = payload.target_ref
    aim_point = payload.aim_point
    selected_target_refs = payload.target_refs
    cast_level = payload.slot_level
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
            reason_code="spell_unavailable",
            spell_id=spell_id,
        )
        return

    cost = spell_action_cost(state, spell)
    block_reason: str | None
    if cast_level is not None and (
        spell.level == 0 or cast_level <= spell.level or cast_level > 9
    ):
        block_reason = "That spell slot level is not available for this spell."
    else:
        block_reason = spell_cast_block_reason_for(
            state,
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
            reason_code=(
                "invalid_spell_level"
                if block_reason
                == "That spell slot level is not available for this spell."
                else "spell_blocked"
            ),
            spell_id=spell.id,
        )
        return

    area = spell_area(
        state,
        actor,
        spell,
        target_ref=target_ref,
        aim_point=aim_point,
    )
    targets = (
        tuple(
            target
            for selected_ref in selected_target_refs
            if (target := spell_target_context(state, actor, selected_ref)) is not None
        )
        if selected_target_refs
        else spell_area_targets(
            state,
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
            reason_code="target_unavailable",
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
            reason_code="spell_unimplemented",
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
            payload=payload,
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
            reason_code="spell_unimplemented",
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
    )


def _record_failed_spell_action(
    state: EncounterState,
    progress: EncounterProgress,
    *,
    creature_ref: str,
    action_id: str,
    message: str,
    reason_code: str,
    spell_id: str | None = None,
) -> None:
    """Record a cast rejected before source-neutral resolution begins."""

    reject_action(
        state,
        progress,
        actor_ref=creature_ref,
        action_id=action_id,
        action_kind="spell",
        message=message,
        reason_code=reason_code,
        details={"spell_id": spell_id} if spell_id is not None else None,
    )


__all__ = ["resolve_spell_action"]
