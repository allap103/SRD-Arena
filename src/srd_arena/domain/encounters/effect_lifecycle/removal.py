"""Remove ongoing effects and undo the runtime modifiers they installed."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ...effects.results import EffectResult
from ...effects.runtime import OngoingEffect
from .movement import reconcile_remaining_movement

if TYPE_CHECKING:
    from ..encounter import EncounterState


def remove_ongoing_effects(state: EncounterState, result: EffectResult) -> None:
    """Remove matching effects from one target according to an effect result."""

    effect_id = result.data.get("effect_id")
    effect_kind = result.data.get("effect_kind")
    parameter = result.data.get("parameter")
    remove_all = bool(result.data.get("all", False))
    matching = tuple(
        effect
        for effect in state.ongoing_effects
        if result.target_ref in effect.target_refs
        and (not isinstance(effect_id, str) or effect.identity.id == effect_id)
        and (not isinstance(effect_kind, str) or effect.kind.value == effect_kind)
        and (
            parameter != "negative_maximum_hit_points"
            or (
                isinstance(
                    maximum_modifier := effect.parameters.get(
                        "maximum_hit_point_modifier"
                    ),
                    int,
                )
                and maximum_modifier < 0
            )
        )
    )
    for effect in matching if remove_all else matching[:1]:
        _remove_effect_target(state, effect, result.target_ref)


def _remove_effect_tree(state: EncounterState, effect: OngoingEffect) -> None:
    """Remove an ongoing effect, every target modifier, and child condition."""

    origin_id = effect.identity.source.origin_id
    for target_ref in effect.target_refs:
        _remove_maximum_hit_point_modifier(state, effect, target_ref)
        _remove_damage_resistances(state, effect, target_ref)
        state.creatures[target_ref].creature.remove_roll_modifiers(
            effect.identity.source.definition_id, origin_id
        )
        state.creatures[target_ref].creature.remove_armor_class_modifier(
            effect.identity.source.definition_id, origin_id
        )
        state.creatures[target_ref].creature.remove_speed_modifier(
            effect.identity.source.definition_id,
            origin_id,
        )
        state.creatures[target_ref].creature.remove_damage_reduction(
            effect.identity.source.definition_id, origin_id
        )
        state.creatures[target_ref].creature.remove_condition_immunities(
            effect.identity.source.definition_id, origin_id
        )
        state.creatures[target_ref].creature.remove_senses(
            effect.identity.source.definition_id, origin_id
        )
    state.ongoing_effects = [
        existing
        for existing in state.ongoing_effects
        if existing.identity.id != effect.identity.id
    ]
    state.conditions = [
        condition
        for condition in state.conditions
        if condition.identity.source.origin_id != origin_id
    ]
    reconcile_remaining_movement(state, effect.target_refs)


def _remove_effect_target(
    state: EncounterState,
    effect: OngoingEffect,
    target_ref: str,
) -> None:
    """Detach one target while retaining a multi-target effect for the rest."""

    _remove_maximum_hit_point_modifier(state, effect, target_ref)
    _remove_damage_resistances(state, effect, target_ref)
    state.creatures[target_ref].creature.remove_roll_modifiers(
        effect.identity.source.definition_id,
        effect.identity.source.origin_id,
    )
    state.creatures[target_ref].creature.remove_armor_class_modifier(
        effect.identity.source.definition_id,
        effect.identity.source.origin_id,
    )
    state.creatures[target_ref].creature.remove_speed_modifier(
        effect.identity.source.definition_id,
        effect.identity.source.origin_id,
    )
    state.creatures[target_ref].creature.remove_damage_reduction(
        effect.identity.source.definition_id,
        effect.identity.source.origin_id,
    )
    state.creatures[target_ref].creature.remove_condition_immunities(
        effect.identity.source.definition_id,
        effect.identity.source.origin_id,
    )
    state.creatures[target_ref].creature.remove_senses(
        effect.identity.source.definition_id,
        effect.identity.source.origin_id,
    )
    remaining_targets = tuple(
        existing for existing in effect.target_refs if existing != target_ref
    )
    state.conditions = [
        condition
        for condition in state.conditions
        if not (
            condition.identity.source.origin_id == effect.identity.source.origin_id
            and condition.target_ref == target_ref
        )
    ]
    if not remaining_targets:
        state.ongoing_effects = [
            existing
            for existing in state.ongoing_effects
            if existing.identity.id != effect.identity.id
        ]
        reconcile_remaining_movement(state, (target_ref,))
        return
    state.ongoing_effects = [
        replace(existing, target_refs=remaining_targets)
        if existing.identity.id == effect.identity.id
        else existing
        for existing in state.ongoing_effects
    ]
    reconcile_remaining_movement(state, (target_ref,))


def _remove_maximum_hit_point_modifier(
    state: EncounterState,
    effect: OngoingEffect,
    target_ref: str,
) -> None:
    modifier = effect.parameters.get("maximum_hit_point_modifier")
    if not isinstance(modifier, int) or modifier == 0:
        return
    state.creatures[target_ref].creature.remove_maximum_health_modifier(
        effect.identity.source.definition_id,
        effect.identity.source.origin_id,
        also_modify_current=bool(
            effect.parameters.get("also_modify_current_hit_points", False)
        ),
    )


def _remove_damage_resistances(
    state: EncounterState,
    effect: OngoingEffect,
    target_ref: str,
) -> None:
    values = effect.parameters.get("damage_resistances", [])
    if not isinstance(values, list):
        return
    for damage_type in values:
        if isinstance(damage_type, str):
            state.creatures[target_ref].creature.remove_damage_resistance(
                damage_type, effect.identity.source.origin_id
            )

