"""Materialize authored ongoing effects in an encounter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...effects.conditions import Condition
from ...effects.modifiers import DamageReduction
from ...effects.results import EffectResult
from ...effects.runtime import (
    EffectPolarity,
    EffectSource,
    EffectSourceKind,
    Indefinite,
    OngoingEffect,
    OngoingEffectKind,
    Rounds,
    RuntimeStateIdentity,
)
from ..attack_economy import reconcile_remaining_attacks
from .concentration import end_concentration
from .movement import reconcile_remaining_movement
from .removal import _remove_effect_tree
from .rule_effects import parse_runtime_rule_effects

if TYPE_CHECKING:
    from ..encounter import EncounterState


def start_ongoing_effect(
    state: EncounterState,
    result: EffectResult,
    origin_id: str,
) -> OngoingEffect:
    """Create an ongoing effect and install its creature modifiers."""

    source_ref = _required_string(result, "source_ref")
    source_label = _required_string(result, "source_label")
    definition_id = _required_string(result, "definition_id")
    kind = OngoingEffectKind(_required_string(result, "effect_kind"))
    polarity = EffectPolarity(str(result.data.get("polarity", "neutral")))
    if kind is OngoingEffectKind.CONCENTRATION:
        end_concentration(state, source_ref)
    source = EffectSource(
        kind=EffectSourceKind.SPELL,
        definition_id=definition_id,
        applied_by_ref=source_ref,
        label=source_label,
        origin_id=origin_id,
    )
    if bool(result.data.get("recast_ends_previous", False)):
        previous = tuple(
            effect
            for effect in state.ongoing_effects
            if effect.identity.source.definition_id == definition_id
            and effect.identity.source.applied_by_ref == source_ref
        )
        for effect in previous:
            _remove_effect_tree(state, effect)
    parameters = result.data.get("parameters")
    duration_rounds = result.data.get("duration_rounds")
    target_refs_data = result.data.get("target_refs")
    target_refs = (
        tuple(ref for ref in target_refs_data if isinstance(ref, str))
        if isinstance(target_refs_data, list)
        else (result.target_ref,)
    )
    effect_parameters = dict(parameters) if isinstance(parameters, dict) else {}
    effect = OngoingEffect(
        identity=RuntimeStateIdentity(
            id=f"ongoing:{kind.value}:{origin_id}",
            source=source,
        ),
        target_refs=target_refs,
        duration=(
            Rounds(duration_rounds)
            if isinstance(duration_rounds, int)
            else Indefinite()
        ),
        kind=kind,
        parameters=effect_parameters,
        polarity=polarity,
        dispellable=True,
        rule_effects=(
            *parse_runtime_rule_effects(effect_parameters),
            *result.rule_effects,
        ),
    )
    state.ongoing_effects.append(effect)
    reconcile_remaining_attacks(state, target_refs)
    reconcile_remaining_movement(state, target_refs)
    _install_creature_modifiers(state, effect)
    return effect


def _install_creature_modifiers(
    state: EncounterState,
    effect: OngoingEffect,
) -> None:
    """Install each modifier encoded by an ongoing effect's parameters."""

    definition_id = effect.identity.source.definition_id
    origin_id = effect.identity.source.origin_id
    maximum_hit_point_modifier = effect.parameters.get("maximum_hit_point_modifier")
    also_modify_current = bool(
        effect.parameters.get("also_modify_current_hit_points", False)
    )
    if isinstance(maximum_hit_point_modifier, int) and maximum_hit_point_modifier:
        for target_ref in effect.target_refs:
            state.creatures[target_ref].creature.set_maximum_health_modifier(
                definition_id,
                origin_id,
                maximum_hit_point_modifier,
                also_modify_current=also_modify_current,
            )
    damage_resistances = effect.parameters.get("damage_resistances", [])
    if isinstance(damage_resistances, list):
        for target_ref in effect.target_refs:
            for damage_type in damage_resistances:
                if isinstance(damage_type, str):
                    state.creatures[target_ref].creature.add_damage_resistance(
                        damage_type, origin_id
                    )
    damage_reduction_type = effect.parameters.get("damage_reduction_type")
    damage_reduction_dice = effect.parameters.get("damage_reduction_dice")
    if isinstance(damage_reduction_type, str) and isinstance(
        damage_reduction_dice, str
    ):
        for target_ref in effect.target_refs:
            state.creatures[target_ref].creature.set_damage_reduction(
                definition_id,
                origin_id,
                DamageReduction(
                    damage_type=damage_reduction_type.casefold(),
                    dice=damage_reduction_dice,
                ),
            )
    condition_immunities = effect.parameters.get("condition_immunities", [])
    if isinstance(condition_immunities, list):
        parsed_immunities = frozenset(
            Condition(value)
            for value in condition_immunities
            if isinstance(value, str)
        )
        for target_ref in effect.target_refs:
            state.creatures[target_ref].creature.set_condition_immunities(
                definition_id, origin_id, parsed_immunities
            )
    senses = effect.parameters.get("senses", [])
    if isinstance(senses, list):
        parsed_senses = tuple(
            (value[0], value[1])
            for value in senses
            if isinstance(value, list)
            and len(value) == 2
            and isinstance(value[0], str)
            and isinstance(value[1], int)
        )
        for target_ref in effect.target_refs:
            state.creatures[target_ref].creature.set_senses(
                definition_id, origin_id, parsed_senses
            )


def _required_string(result: EffectResult, key: str) -> str:
    value = result.data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Ongoing effect requires string {key}.")
    return value
