"""Resolve persistent area effects when a creature starts its turn inside them."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from srd_arena.domain.effects.conditions import build_applied_condition
from srd_arena.domain.effects.runtime import (
    EffectSource,
    OngoingEffect,
    RuntimeStateIdentity,
    UntilTurnEnd,
)
from srd_arena.domain.rolls.dice import D20RollMode
from srd_arena.domain.rolls.saving_throws import Ability, resolve_saving_throw

from ..condition_state import apply_condition
from ..rule_queries.defenses import (
    condition_immunities,
    has_condition_save_advantage,
)
from ..rule_queries.rolls import roll_modifiers
from ..spatial import creature_occupied_cells
from ..state_combat import automatic_save_failure_provider_ids_for
from ..state_runtime import create_event
from .roll_usage import resolve_saving_throw_modifier

if TYPE_CHECKING:
    from ..encounter import EncounterState
    from ..encounter_models.resolution import EncounterProgress


def resolve_turn_start_area_effects(
    state: EncounterState,
    creature_ref: str,
    progress: EncounterProgress | None = None,
) -> None:
    """Resolve every persistent area containing the starting creature."""

    occupied = {
        (cell.x, cell.y) for cell in creature_occupied_cells(state, creature_ref)
    }
    matching = tuple(
        effect
        for effect in state.ongoing_effects
        if effect.area is not None
        and effect.lifecycle.area_turn_start_save is not None
        and any((cell.x, cell.y) in occupied for cell in effect.area.cells)
    )
    for effect in matching:
        _resolve_area_save(state, effect, creature_ref, progress)


def _resolve_area_save(
    state: EncounterState,
    effect: OngoingEffect,
    creature_ref: str,
    progress: EncounterProgress | None,
) -> None:
    save_rule = effect.lifecycle.area_turn_start_save
    assert save_rule is not None
    creature = state.creatures[creature_ref].creature
    effect_label = (
        effect.label or effect.identity.source.definition_id.replace("_", " ").title()
    )
    immune_conditions = condition_immunities(state, creature_ref).values
    negating_immunity = save_rule.negated_by_condition_immunity
    if negating_immunity is not None and negating_immunity in immune_conditions:
        reasons = (f"{effect_label}: immune to {negating_immunity.value}",)
        _publish_result(
            state,
            effect,
            creature_ref,
            progress,
            success=True,
            save_detail={
                "target_ref": creature_ref,
                "target_label": creature.name,
                "ability": save_rule.ability,
                "target_dc": save_rule.dc,
                "success": True,
                "automatic_success_reasons": list(reasons),
                "automatic_failure_reasons": [],
            },
        )
        return

    save_mode: D20RollMode = (
        "advantage"
        if has_condition_save_advantage(
            state,
            creature_ref,
            tuple(condition.value for condition in save_rule.failure_conditions),
        )
        else "normal"
    )
    roll_rules = roll_modifiers(
        state,
        creature_ref,
        "saving_throw",
        ability=save_rule.ability,
    )
    save = resolve_saving_throw(
        creature,
        cast(Ability, save_rule.ability),
        save_rule.dc,
        mode=save_mode,
        sourced_modifier_override=resolve_saving_throw_modifier(
            state,
            creature_ref,
            roll_rules,
        ),
        sourced_mode_override=roll_rules.mode,
        roller=state.dice.roll_die,
        automatic_failure_reasons=automatic_save_failure_provider_ids_for(
            state,
            creature_ref,
            save_rule.ability,
        ),
    )
    if not save.check.success:
        _apply_failed_save(state, effect, creature_ref, progress)
    _publish_result(
        state,
        effect,
        creature_ref,
        progress,
        success=save.check.success,
        save_detail={
            "target_ref": creature_ref,
            "target_label": creature.name,
            "ability": save_rule.ability,
            "die": save.check.roll.selected,
            "dice": list(save.check.roll.dice),
            "selected_index": save.check.roll.selected_index,
            "modifier": save.modifiers.total,
            "total": save.check.roll.total,
            "target_dc": save.check.target,
            "success": save.check.success,
            "automatic_success_reasons": [],
            "automatic_failure_reasons": list(save.automatic_failure_reasons),
        },
    )


def _apply_failed_save(
    state: EncounterState,
    effect: OngoingEffect,
    creature_ref: str,
    progress: EncounterProgress | None,
) -> None:
    save_rule = effect.lifecycle.area_turn_start_save
    assert save_rule is not None
    source = effect.identity.source
    child_origin = f"{source.origin_id}:turn:{state.round.number}:target:{creature_ref}"
    child_id = f"{effect.identity.id}:turn:{state.round.number}:{creature_ref}"
    child_source = EffectSource(
        kind=source.kind,
        definition_id=source.definition_id,
        applied_by_ref=source.applied_by_ref,
        label=source.label,
        origin_id=child_origin,
    )
    duration = UntilTurnEnd(creature_ref, state.round.number)
    child = OngoingEffect(
        identity=RuntimeStateIdentity(
            id=child_id,
            source=child_source,
            parent_id=effect.identity.id,
            root_id=effect.identity.root_id,
        ),
        target_refs=(creature_ref,),
        duration=duration,
        kind=effect.kind,
        polarity=effect.polarity,
        label=effect.label,
        rule_effects=save_rule.failure_rule_effects,
    )
    state.ongoing_effects = [
        existing
        for existing in state.ongoing_effects
        if existing.identity.id != child_id
    ]
    state.ongoing_effects.append(child)
    source_ref = source.applied_by_ref or "system"
    for condition in save_rule.failure_conditions:
        result = apply_condition(
            state,
            build_applied_condition(
                condition=condition,
                source_ref=source_ref,
                source_label=source.label or effect.label or "Area effect",
                target_ref=creature_ref,
                duration=duration,
                source_kind=source.kind,
                definition_id=source.definition_id,
                origin_id=child_origin,
                parent_id=child_id,
                root_id=effect.identity.root_id,
            ),
        )
        if progress is not None and source.definition_id == "stinking_cloud":
            for applied in result.applied:
                progress.events.append(
                    create_event(
                        state,
                        "condition_manifested",
                        creature_ref=creature_ref,
                        data={
                            "condition_id": applied.id,
                            "condition": applied.condition.value,
                            "manifestation": "stinking_cloud_retching",
                        },
                    )
                )
    if progress is not None and source.definition_id == "stinking_cloud":
        progress.events.append(
            create_event(
                state,
                "effect_manifested",
                creature_ref=creature_ref,
                data={
                    "effect_id": child_id,
                    "definition_id": source.definition_id,
                    "manifestation": "stinking_cloud_retching",
                },
            )
        )


def _publish_result(
    state: EncounterState,
    effect: OngoingEffect,
    creature_ref: str,
    progress: EncounterProgress | None,
    *,
    success: bool,
    save_detail: dict[str, object],
) -> None:
    if progress is None:
        return
    creature = state.creatures[creature_ref].creature
    label = effect.label or effect.identity.source.definition_id
    outcome = "succeeds" if success else "fails"
    progress.messages.append(
        (
            "system",
            f"{creature.name} {outcome} on the {str(save_detail['ability']).title()} "
            f"save against {label}.",
        )
    )
    progress.events.append(
        create_event(
            state,
            "ongoing_area_effect_resolved",
            creature_ref=creature_ref,
            data={
                "effect_id": effect.identity.id,
                "spell_id": effect.identity.source.definition_id,
                "spell_name": label,
                "save_detail": save_detail,
            },
        )
    )
