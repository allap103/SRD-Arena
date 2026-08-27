"""Build ongoing-effect and condition results from resolved spell targets."""

from ...capabilities import (
    ArmorClassModifierEffect,
    ConditionImmunityEffect,
    ConditionSaveAdvantageEffect,
    DamageReductionEffect,
    DamageResistanceEffect,
    EffectDuration,
    HitPointMaximumModifierEffect,
    SenseEffect,
    SpeedModifierEffect,
)
from ...effects.results import EffectResult
from ..rules import spell_duration_rounds
from .context import SpellActionContext
from .details import effect_duration_rounds, serialize_roll_modifiers
from .polarity import persistent_spell_effect_polarity
from .preparation import PreparedSpellResolution
from .scaling import resource_dice_increment, resource_int_increment, scale_dice
from .targets import ResolvedSpellTargets


def build_persistent_spell_effects(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
    resolved: ResolvedSpellTargets,
) -> list[EffectResult]:
    """Create ongoing effects that retain the casting source and future rules hooks."""

    spell = context.spell
    assert context.creature.spellcasting is not None

    selected_condition = context.selected_condition
    if selected_condition not in prepared.conditions:
        selected_condition = prepared.conditions[0] if prepared.conditions else None
    selected_conditions = (
        ((selected_condition,) if selected_condition is not None else ())
        if prepared.definition.condition_selection == "choose_one"
        else prepared.conditions
    )
    parent_kind = "concentration" if spell.concentration else "spell"
    duration_rounds = spell_duration_rounds(spell)
    maximum_hit_point_effect = next(
        (
            effect
            for effect in prepared.definition_effects
            if isinstance(effect, HitPointMaximumModifierEffect)
        ),
        None,
    )
    maximum_hit_point_modifier = (
        maximum_hit_point_effect.value if maximum_hit_point_effect is not None else 0
    ) + (
        resource_int_increment(prepared.definition, "hit_point_maximum")
        * prepared.levels_above
    )
    resistance_effect = next(
        (
            effect
            for effect in prepared.definition_effects
            if isinstance(effect, DamageResistanceEffect)
        ),
        None,
    )
    selected_damage_resistances = (
        resistance_effect.damage_types if resistance_effect is not None else ()
    )
    if resistance_effect is not None and resistance_effect.selection == "choose_one":
        selected_damage_resistances = (
            (context.selected_damage_type,)
            if context.selected_damage_type in resistance_effect.damage_types
            else resistance_effect.damage_types[:1]
        )
    reduction_effect = next(
        (
            effect
            for effect in prepared.definition_effects
            if isinstance(effect, DamageReductionEffect)
        ),
        None,
    )
    selected_damage_reduction_type = None
    if reduction_effect is not None:
        selected_damage_reduction_type = (
            context.selected_damage_type
            if context.selected_damage_type in reduction_effect.damage_types
            else reduction_effect.damage_types[0]
        )
    condition_save_advantages = tuple(
        condition
        for effect in prepared.definition_effects
        if isinstance(effect, ConditionSaveAdvantageEffect)
        for condition in effect.conditions
    )
    armor_class_modifier = sum(
        effect.value
        for effect in prepared.definition_effects
        if isinstance(effect, ArmorClassModifierEffect)
    )
    speed_modifier_feet = sum(
        effect.feet
        for effect in prepared.definition_effects
        if isinstance(effect, SpeedModifierEffect)
    )
    condition_immunities = tuple(
        condition
        for effect in prepared.definition_effects
        if isinstance(effect, ConditionImmunityEffect)
        for condition in effect.conditions
    )
    senses = tuple(
        (effect.sense, effect.range_feet)
        for effect in prepared.definition_effects
        if isinstance(effect, SenseEffect)
    )
    effect_duration = next(
        (
            duration
            for effect in prepared.definition_effects
            for duration in (getattr(effect, "duration", None),)
            if isinstance(duration, EffectDuration)
        ),
        None,
    )

    effects: list[EffectResult] = []
    if (
        resolved.affected_targets
        and (
            prepared.conditions
            or maximum_hit_point_modifier != 0
            or selected_damage_resistances
            or condition_save_advantages
            or prepared.roll_modifier_effects
            or armor_class_modifier
            or speed_modifier_feet
            or selected_damage_reduction_type is not None
            or any(
                temporary.trigger == "target_turn_start"
                for temporary in prepared.temporary_hit_point_effects
            )
            or condition_immunities
            or senses
        )
        and (
            duration_rounds is not None
            or spell.concentration
            or prepared.repeat_save is not None
        )
    ):
        effects.append(
            EffectResult(
                kind="start_ongoing_effect",
                target_ref=resolved.affected_targets[0].target_ref,
                data={
                    "effect_kind": parent_kind,
                    "source_ref": context.source_ref,
                    "polarity": persistent_spell_effect_polarity(
                        prepared,
                    ).value,
                    "source_label": context.creature.name,
                    "definition_id": spell.id,
                    "recast_ends_previous": spell.recast_ends_previous,
                    "target_refs": [
                        target.target_ref for target in resolved.affected_targets
                    ],
                    "duration_rounds": (
                        duration_rounds
                        if duration_rounds is not None
                        else effect_duration_rounds(effect_duration)
                    ),
                    "parameters": {
                        "effect_label": spell.name,
                        "started_round": context.current_round,
                        "repeat_save_trigger": (
                            prepared.repeat_save.trigger
                            if prepared.repeat_save is not None
                            else None
                        ),
                        "save_ability": (
                            prepared.repeat_save.ability
                            if prepared.repeat_save is not None
                            else prepared.save_ability
                        ),
                        "save_dc": context.creature.spellcasting.save_dc,
                        "repeat_failure_conditions": list(
                            prepared.repeat_failure_conditions
                        ),
                        "repeat_failure_damage": [
                            {
                                "dice": scale_dice(
                                    damage.dice,
                                    resource_dice_increment(
                                        prepared.definition,
                                        "damage_dice",
                                        damage.damage_type,
                                    ),
                                    prepared.levels_above,
                                ),
                                "damage_type": damage.damage_type,
                            }
                            for damage in prepared.repeat_failure_damage
                        ],
                        "end_events": [list(event) for event in prepared.end_events],
                        "damage_repeat_save_advantage": (
                            prepared.damage_repeat_save_advantage
                        ),
                        "maximum_hit_point_modifier": maximum_hit_point_modifier,
                        "also_modify_current_hit_points": (
                            maximum_hit_point_effect.also_modify_current
                            if maximum_hit_point_effect is not None
                            else False
                        ),
                        "damage_resistances": list(selected_damage_resistances),
                        "condition_save_advantages": list(condition_save_advantages),
                        "roll_modifiers": serialize_roll_modifiers(
                            prepared.roll_modifier_effects,
                            context.selected_ability,
                        ),
                        "armor_class_modifier": armor_class_modifier,
                        "speed_modifier_feet": speed_modifier_feet,
                        "damage_reduction_type": selected_damage_reduction_type,
                        "damage_reduction_dice": (
                            reduction_effect.dice
                            if reduction_effect is not None
                            else None
                        ),
                        "turn_start_temporary_hit_points": next(
                            (
                                temporary.value
                                + (
                                    context.creature.spellcasting.ability_modifier
                                    if temporary.modifier == "ability_modifier"
                                    else 0
                                )
                                for temporary in prepared.temporary_hit_point_effects
                                if temporary.trigger == "target_turn_start"
                            ),
                            0,
                        ),
                        "condition_immunities": list(condition_immunities),
                        "senses": [list(sense) for sense in senses],
                    },
                },
            )
        )

    for target in resolved.affected_targets:
        for condition in selected_conditions:
            condition_data: dict[str, object] = {
                "condition": condition,
                "source_ref": context.source_ref,
                "source_label": context.creature.name,
                "source_kind": "spell",
                "definition_id": spell.id,
            }
            if condition in spell.self_removal_blocked_conditions:
                condition_data["metadata"] = {"blocks_self_removal": True}
            if effects:
                condition_data["parent_effect_kind"] = parent_kind
            if prepared.expires_on_source_turn_end:
                condition_data["expires_on_creature_ref"] = context.source_ref
                condition_data["expires_on_round"] = context.current_round + 1
            effects.append(
                EffectResult(
                    kind="apply_condition",
                    target_ref=target.target_ref,
                    data=condition_data,
                )
            )
    return effects
