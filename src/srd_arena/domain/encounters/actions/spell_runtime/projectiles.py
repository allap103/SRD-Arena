"""Suspend and resume repeated spell attacks around per-hit decisions."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from srd_arena.domain.creatures.feature_rules import (
    spell_invocation_grant,
)
from srd_arena.domain.effects.results import (
    ActionResolutionResult,
    SpellResolutionDetails,
)
from srd_arena.domain.spells.resolution import (
    SpellTargetContext,
    resolve_spell_action,
)

from ...encounter_models.decisions import (
    PendingSpellProjectiles,
    ResumeSpellProjectiles,
)
from ...encounter_models.resolution import EncounterProgress
from ...state_runtime import create_event
from ..d20_roll_modifiers import clear_d20_roll_modes
from ..eligibility_rules.common import target_requirement_failure
from ..eligibility_rules.spell_targeting import spell_target_eligibility
from ..feature_runtime.repelling_blast import (
    repelling_blast_effect,
    resolve_repelling_blast_hit,
)
from ..option_discovery.spell_targets import spell_action_targets
from .aftermath import apply_spell_result_consequences, publish_spell_result
from .context import build_spell_action_context

if TYPE_CHECKING:
    from srd_arena.domain.creatures import Creature
    from srd_arena.domain.spells import Spell
    from srd_arena.domain.spells.action_payloads import SpellActionPayload

    from ...encounter import EncounterState


def spell_requires_projectile_staging(caster: Creature, spell: Spell) -> bool:
    """Return whether this casting has a supported interruptible hit trigger."""

    return (
        spell.definition is not None
        and repelling_blast_effect(caster, spell) is not None
    )


def begin_spell_projectiles(
    state: EncounterState,
    *,
    caster: Creature,
    spell: Spell,
    payload: SpellActionPayload,
    targets: tuple[SpellTargetContext, ...],
    cast_level: int | None,
    caster_ref: str,
    action_id: str,
    progress: EncounterProgress,
) -> None:
    """Start a durable repeated-spell occurrence and resolve its first projectile."""

    invocation = PendingSpellProjectiles(
        invocation_id=action_id,
        caster_ref=caster_ref,
        spell_id=spell.id,
        cast_level=cast_level,
        payload=payload,
        target_refs=tuple(target.target_ref for target in targets),
        target_labels=tuple(target.target_label for target in targets),
        remaining_target_refs=[target.target_ref for target in targets],
    )
    resume_spell_projectiles(state, invocation, progress)


def resume_spell_projectiles(
    state: EncounterState,
    invocation: PendingSpellProjectiles,
    progress: EncounterProgress,
) -> None:
    """Resolve projectiles in order until a choice pauses or the spell completes."""

    caster = state.creatures[invocation.caster_ref].creature
    spellcasting = caster.spellcasting
    if spellcasting is None:
        raise RuntimeError("A staged spell invocation lost its spellcasting source.")
    grant = spell_invocation_grant(caster, invocation.payload.grant_id)
    spell = spellcasting.spell_for_grant(invocation.spell_id, grant)
    if spell is None or spell.definition is None:
        raise RuntimeError("A staged spell invocation lost its spell definition.")

    while invocation.remaining_target_refs:
        target_ref = invocation.remaining_target_refs.pop(0)
        projectile_index = len(invocation.target_refs) - len(
            invocation.remaining_target_refs
        )
        target, failure_code = _live_projectile_target(
            state,
            caster,
            spell,
            invocation.caster_ref,
            target_ref,
        )
        if target is None:
            _record_skipped_projectile(
                state,
                invocation,
                target_ref,
                projectile_index,
                failure_code,
                progress,
            )
            continue
        projectile_payload = replace(invocation.payload, target_refs=(target_ref,))
        result = resolve_spell_action(
            build_spell_action_context(
                state,
                actor=caster,
                spell=spell,
                payload=projectile_payload,
                creature_ref=invocation.caster_ref,
                target=target,
                targets=(target,),
                area=None,
                cast_level=invocation.cast_level,
                action_id=invocation.invocation_id,
                roll_occurrence_index_offset=projectile_index - 1,
                announce_cast=not invocation.cast_announced,
                maximize_temporary_hit_point_dice=(
                    grant is not None and grant.temporary_hit_point_dice == "maximum"
                ),
            )
        )
        if result is None:
            raise RuntimeError("A staged spell projectile could not be resolved.")
        result = _set_projectile_index(result, projectile_index)
        invocation.resolved_results.append(result)
        apply_spell_result_consequences(
            state,
            result=result,
            creature_ref=invocation.caster_ref,
            action_id=invocation.invocation_id,
            progress=progress,
        )
        invocation.cast_announced = True
        publish_spell_result(
            state,
            spellcasting=spellcasting,
            spell=spell,
            cast_level=invocation.cast_level,
            creature_ref=invocation.caster_ref,
            action_id=invocation.invocation_id,
            result=result,
            progress=progress,
            event_type="spell_projectile_resolved",
            additional_data={"projectile_index": projectile_index},
            grant_id=grant.id if grant is not None else None,
            consumes_spell_slot=(
                grant.consumes_spell_slot if grant is not None else True
            ),
        )
        if resolve_repelling_blast_hit(
            state,
            caster=caster,
            spell=spell,
            caster_ref=invocation.caster_ref,
            action_id=invocation.invocation_id,
            result=result,
            progress=progress,
            continuation=ResumeSpellProjectiles(invocation),
        ):
            return

    publish_spell_result(
        state,
        spellcasting=spellcasting,
        spell=spell,
        cast_level=invocation.cast_level,
        creature_ref=invocation.caster_ref,
        action_id=invocation.invocation_id,
        result=_merge_projectile_results(invocation, spell),
        progress=progress,
        include_resolution_details=False,
        additional_data={
            "projectile_count": len(invocation.target_refs),
            "resolved_projectile_count": len(invocation.resolved_results),
        },
        grant_id=grant.id if grant is not None else None,
        consumes_spell_slot=(grant.consumes_spell_slot if grant is not None else True),
    )
    clear_d20_roll_modes(state, invocation.invocation_id)


def _live_projectile_target(
    state: EncounterState,
    caster: Creature,
    spell: Spell,
    caster_ref: str,
    target_ref: str,
) -> tuple[SpellTargetContext | None, str]:
    available = {
        target.target_ref: target
        for target in spell_action_targets(state, caster, spell)
    }
    target = available.get(target_ref)
    if target is None:
        return None, "target_unavailable"
    eligibility = spell_target_eligibility(state, caster_ref, target_ref, spell)
    if not eligibility.allowed:
        return None, eligibility.failures[0].code
    assert spell.definition is not None
    requirement_failure = target_requirement_failure(
        state,
        caster_ref,
        target_ref,
        spell.definition.target.requirements,
    )
    if requirement_failure is not None:
        return None, requirement_failure.code
    return target, ""


def _record_skipped_projectile(
    state: EncounterState,
    invocation: PendingSpellProjectiles,
    target_ref: str,
    projectile_index: int,
    reason_code: str,
    progress: EncounterProgress,
) -> None:
    target_label = (
        state.creatures[target_ref].creature.name
        if target_ref in state.creatures
        else target_ref
    )
    progress.messages.append(
        (
            "system",
            f"{invocation.spell_id.replace('_', ' ').title()} projectile "
            f"{projectile_index} cannot affect {target_label}.",
        )
    )
    progress.events.append(
        create_event(
            state,
            "spell_projectile_skipped",
            creature_ref=invocation.caster_ref,
            action_id=invocation.invocation_id,
            data={
                "spell_id": invocation.spell_id,
                "projectile_index": projectile_index,
                "target_ref": target_ref,
                "reason_code": reason_code,
            },
        )
    )


def _set_projectile_index(
    result: ActionResolutionResult,
    projectile_index: int,
) -> ActionResolutionResult:
    details = result.details
    if not isinstance(details, SpellResolutionDetails):
        raise TypeError("A staged spell projectile returned non-spell details.")
    return replace(
        result,
        details=replace(
            details,
            attack_roll_details=tuple(
                {**detail, "projectile_index": projectile_index}
                for detail in details.attack_roll_details
            ),
        ),
    )


def _merge_projectile_results(
    invocation: PendingSpellProjectiles,
    spell: Spell,
) -> ActionResolutionResult:
    details = tuple(
        result.details
        for result in invocation.resolved_results
        if isinstance(result.details, SpellResolutionDetails)
    )
    cast_level = (
        invocation.cast_level if invocation.cast_level is not None else spell.level
    )
    merged_details = SpellResolutionDetails(
        target_ref=invocation.target_refs[0],
        target_label=invocation.target_labels[0],
        targets=tuple(
            zip(invocation.target_refs, invocation.target_labels, strict=True)
        ),
        affected_target_refs=tuple(
            target_ref
            for detail in details
            for target_ref in detail.affected_target_refs
        ),
        area=None,
        spell_level=spell.level,
        slot_level=cast_level,
        save_details=tuple(item for detail in details for item in detail.save_details),
        attack_roll_details=tuple(
            item for detail in details for item in detail.attack_roll_details
        ),
        damage_roll_details=tuple(
            item for detail in details for item in detail.damage_roll_details
        ),
        healing_roll_details=tuple(
            item for detail in details for item in detail.healing_roll_details
        ),
        temporary_hit_point_details=tuple(
            item for detail in details for item in detail.temporary_hit_point_details
        ),
        damage_applications=tuple(
            item for detail in details for item in detail.damage_applications
        ),
        success=any(detail.success for detail in details),
    )
    return ActionResolutionResult(
        spell.id,
        spell.name,
        [],
        [effect for result in invocation.resolved_results for effect in result.effects],
        resource_updates={
            key: value
            for result in invocation.resolved_results
            for key, value in result.resource_updates.items()
        },
        details=merged_details,
    )
