"""Assemble loaded spells from authored content.

The translator has three jobs: resolve the authored spell, compile intrinsic
spell metadata and the shared executable capability definition, and produce the
legacy ``SpellCapability`` projection still consumed by the encounter runtime.
Provider-specific grants and resource costs do not belong here.

Keep ``build_spell`` as the readable orchestration entrypoint. New translation
rules belong in the concern-based ``translation`` package; the remaining legacy
projection should shrink as runtime consumers move to shared capabilities.
"""

from typing import cast

from .catalog import SpellCatalog
from .schema import SpellSchema
from srd_arena.content.capabilities import (
    ConditionEffectSchema,
    DamageEffectSchema,
    RollModifierEffectSchema,
)
from .resolution import (
    ArmorClassModifierEffectSchema,
    AutomaticResolutionSchema,
    ConditionSaveAdvantageEffectSchema,
    ConditionImmunityEffectSchema,
    HealingEffectSchema,
    HitPointMaximumModifierEffectSchema,
    DamageResistanceEffectSchema,
    DamageReductionEffectSchema,
    RepeatResolutionSchema,
    SavingThrowResolutionSchema,
    SenseEffectSchema,
    SpeedModifierEffectSchema,
    SequenceResolutionSchema,
    SpellAttackResolutionSchema,
    TemporaryHitPointsEffectSchema,
)
from srd_arena.content.common.sources import slug
from srd_arena.domain.spells import (
    SpellCapability,
    Spell,
    SpellDamage,
    SpellHealing,
    SpellTemporaryHitPoints,
)
from srd_arena.domain.effects.modifiers import (
    ModifierMode,
    ModifierSubject,
    RollKind,
    RollModifier,
)
from .translation import (
    automatic_success_condition_immunities,
    automatic_success_traits,
    cantrip_damage_by_level,
    compile_activation,
    compile_definition,
    creature_types_from_requirements,
    damage_repeat_save_advantage,
    effect_duration_rounds,
    end_events,
    find_spell,
    normalize_save_ability,
    repeat_failure_conditions,
    repeat_failure_damage,
    repeat_save_trigger,
    save_advantage_against_opponents,
    slot_damage_increment,
    slot_scaling_value,
    slot_target_increment,
    spell_duration_rounds,
    target_count_by_caster_level,
    target_requirements,
)


from .translation.metadata import (
    remove_effect_selection,
    spell_area_size_feet,
    spell_damage_dice,
    spell_geometry_mode,
    spell_removable_conditions,
    spell_removable_effect_kinds,
)
from .translation.follow_ups import follow_up_resolution


def build_spell(
    name: str,
    source: str | None,
    catalog: SpellCatalog | None,
) -> Spell:
    raw = find_spell(name, source, catalog)
    capability = _translate_capability(raw)
    return Spell(
        id=slug(raw.public_name),
        name=raw.public_name,
        source=raw.source,
        level=raw.level,
        school=raw.school,
        casting_time=tuple(raw.time),
        range_data=dict(raw.range),
        duration_data=tuple(raw.duration),
        components=dict(raw.components),
        saving_throw_abilities=tuple(
            normalize_save_ability(value) for value in raw.saving_throw
        ),
        condition_inflict=tuple(raw.condition_inflict),
        removable_conditions=spell_removable_conditions(raw),
        removable_effect_kinds=spell_removable_effect_kinds(raw),
        remove_effect_selection=remove_effect_selection(raw),
        damage_dice=spell_damage_dice(raw),
        damage_inflict=tuple(raw.damage_inflict),
        area_tags=tuple(raw.area_tags),
        geometry_mode=spell_geometry_mode(raw),
        area_size_feet=spell_area_size_feet(raw),
        concentration=any(
            bool(duration.get("concentration"))
            for duration in raw.duration
            if isinstance(duration, dict)
        ),
        target_requirements=target_requirements(raw),
        capability=capability,
        activation=compile_activation(raw),
    )


def _translate_capability(raw: SpellSchema) -> SpellCapability | None:
    if raw.capability is None:
        return None
    target = raw.capability.target
    outer_resolution = raw.capability.resolution.root
    sequence = (
        outer_resolution
        if isinstance(outer_resolution, SequenceResolutionSchema)
        else None
    )
    if sequence is not None:
        outer_resolution = sequence.steps[0].resolution.root
    repeated = (
        outer_resolution
        if isinstance(outer_resolution, RepeatResolutionSchema)
        else None
    )
    resolution = repeated.resolution.root if repeated is not None else outer_resolution
    if not isinstance(
        resolution,
        (
            AutomaticResolutionSchema,
            SavingThrowResolutionSchema,
            SpellAttackResolutionSchema,
        ),
    ):
        return None
    if isinstance(resolution, SavingThrowResolutionSchema):
        outcome = resolution.failure
    elif isinstance(resolution, SpellAttackResolutionSchema):
        outcome = resolution.hit
    else:
        outcome = resolution.outcome
    damage = tuple(
        SpellDamage(effect.root.dice, effect.root.damage_type)
        for effect in outcome.effects
        if isinstance(effect.root, DamageEffectSchema)
    )
    conditions = tuple(
        effect.root.condition
        for effect in outcome.effects
        if isinstance(effect.root, ConditionEffectSchema)
    )
    healing = tuple(
        SpellHealing(
            dice=effect.root.dice,
            bonus=effect.root.bonus,
            add_spellcasting_modifier=effect.root.modifier == "spellcasting_ability",
            restore_to_maximum=effect.root.restore_to_maximum,
            pool=effect.root.pool,
        )
        for effect in outcome.effects
        if isinstance(effect.root, HealingEffectSchema)
    )
    temporary_hit_points = tuple(
        SpellTemporaryHitPoints(
            dice=effect.root.dice,
            value=effect.root.value,
            add_spellcasting_modifier=effect.root.modifier == "spellcasting_ability",
            trigger=effect.root.trigger,
        )
        for effect in outcome.effects
        if isinstance(effect.root, TemporaryHitPointsEffectSchema)
    )
    maximum_hit_point_modifier = next(
        (
            effect.root
            for effect in outcome.effects
            if isinstance(effect.root, HitPointMaximumModifierEffectSchema)
        ),
        None,
    )
    armor_class_modifier = next(
        (
            effect.root.value
            for effect in outcome.effects
            if isinstance(effect.root, ArmorClassModifierEffectSchema)
        ),
        0,
    )
    speed_modifier = next(
        (
            effect.root
            for effect in outcome.effects
            if isinstance(effect.root, SpeedModifierEffectSchema)
        ),
        None,
    )
    damage_resistances = tuple(
        damage_type
        for effect in outcome.effects
        if isinstance(effect.root, DamageResistanceEffectSchema)
        for damage_type in effect.root.damage_types
    )
    damage_resistance_choice = any(
        isinstance(effect.root, DamageResistanceEffectSchema)
        and effect.root.selection == "choose_one"
        for effect in outcome.effects
    )
    damage_reduction = next(
        (
            effect.root
            for effect in outcome.effects
            if isinstance(effect.root, DamageReductionEffectSchema)
        ),
        None,
    )
    condition_save_advantages = tuple(
        condition
        for effect in outcome.effects
        if isinstance(effect.root, ConditionSaveAdvantageEffectSchema)
        for condition in effect.root.conditions
    )
    condition_immunities = tuple(
        condition
        for effect in outcome.effects
        if isinstance(effect.root, ConditionImmunityEffectSchema)
        for condition in effect.root.conditions
    )
    senses = tuple(
        (effect.root.sense, effect.root.range_feet)
        for effect in outcome.effects
        if isinstance(effect.root, SenseEffectSchema)
    )
    roll_modifiers = tuple(
        RollModifier(
            roll=cast(RollKind, roll),
            mode=cast(ModifierMode, effect.root.mode),
            dice=effect.root.dice,
            value=effect.root.value,
            subject=cast(ModifierSubject, effect.root.subject),
            ignored_by_senses=tuple(effect.root.ignored_by_senses),
            ability=(normalize_save_ability(ability) if ability is not None else None),
        )
        for effect in outcome.effects
        if isinstance(effect.root, RollModifierEffectSchema)
        for roll in (
            ("ability_check", "attack_roll", "saving_throw")
            if effect.root.roll == "d20_test"
            else (effect.root.roll,)
        )
        for ability in (
            tuple(effect.root.ability_options)
            if effect.root.ability_options
            else (effect.root.ability,)
        )
    )
    geometry = target.geometry if target.type == "area" else None
    return SpellCapability(
        resolution=resolution.type,
        target=target.type,
        damage=damage,
        save_ability=(
            normalize_save_ability(resolution.ability)
            if isinstance(resolution, SavingThrowResolutionSchema)
            and resolution.ability is not None
            else raw.saving_throw[0]
            if raw.saving_throw
            else None
        ),
        attack_mode=(
            resolution.mode
            if isinstance(resolution, SpellAttackResolutionSchema)
            else None
        ),
        half_damage_on_save=(
            isinstance(resolution, SavingThrowResolutionSchema)
            and resolution.success_damage == "half"
        ),
        area_shape=geometry.shape if geometry is not None else None,
        area_radius_feet=geometry.radius_feet if geometry is not None else None,
        area_length_feet=geometry.length_feet if geometry is not None else None,
        area_width_feet=geometry.width_feet if geometry is not None else None,
        area_height_feet=geometry.height_feet if geometry is not None else None,
        automatic_failure_creature_types=(
            creature_types_from_requirements(resolution.automatic_failure)
            if isinstance(resolution, SavingThrowResolutionSchema)
            else ()
        ),
        disadvantage_creature_types=(
            tuple(
                creature_type
                for modifier in resolution.save_modifiers
                if modifier.mode == "disadvantage"
                for creature_type in creature_types_from_requirements(
                    modifier.requirements
                )
            )
            if isinstance(resolution, SavingThrowResolutionSchema)
            else ()
        ),
        cantrip_damage_by_level=cantrip_damage_by_level(raw),
        slot_damage_increment=slot_damage_increment(
            raw,
            damage_types={damage.damage_type for damage in damage},
        ),
        conditions=conditions,
        condition_choice=raw.capability.condition_application == "choose_one",
        duration_rounds=spell_duration_rounds(raw),
        concentration=any(
            bool(duration.get("concentration"))
            for duration in raw.duration
            if isinstance(duration, dict)
        ),
        repeat_save_trigger=repeat_save_trigger(resolution),
        expires_on_source_turn_end=any(
            isinstance(effect.root, ConditionEffectSchema)
            and effect.root.duration is not None
            and effect.root.duration.type == "end_of_turn"
            and effect.root.duration.creature == "source"
            for effect in outcome.effects
        ),
        target_disposition=(target.disposition if target.type == "creature" else "any"),
        repeat_failure_conditions=repeat_failure_conditions(resolution),
        repeat_failure_damage=repeat_failure_damage(resolution),
        end_events=end_events(raw),
        damage_repeat_save_advantage=damage_repeat_save_advantage(raw),
        save_advantage_against_opponents=(
            save_advantage_against_opponents(resolution)
        ),
        automatic_success_condition_immunities=(
            automatic_success_condition_immunities(resolution)
        ),
        automatic_success_traits=automatic_success_traits(resolution),
        self_removal_blocked_conditions=tuple(
            raw.capability.self_removal_blocked_conditions
        ),
        base_target_count=(
            target_count_by_caster_level(raw)[0][1]
            if target_count_by_caster_level(raw)
            else repeated.count
            if repeated is not None and isinstance(repeated.count, int)
            else target.count.maximum
            if target.type == "creature" and isinstance(target.count.maximum, int)
            else 1
        ),
        slot_target_increment=slot_target_increment(raw),
        choose_area_targets=(target.type == "area" and target.occupants == "chosen"),
        repeat_target_allocations=(
            repeated is not None
            and repeated.allocation in {"same_target", "same_or_different"}
        ),
        require_full_target_count=repeated is not None,
        target_count_by_caster_level=target_count_by_caster_level(raw),
        follow_up_resolutions=(
            tuple(follow_up_resolution(raw, step) for step in sequence.steps[1:])
            if sequence is not None
            else ()
        ),
        healing=healing,
        temporary_hit_points=temporary_hit_points,
        slot_healing_dice_increment=slot_scaling_value(raw, "healing_dice", str),
        slot_healing_bonus_increment=(
            slot_scaling_value(raw, "healing_bonus", int) or 0
        ),
        slot_temporary_hit_points_increment=(
            slot_scaling_value(raw, "temporary_hit_points", int) or 0
        ),
        maximum_hit_point_modifier=(
            maximum_hit_point_modifier.value
            if maximum_hit_point_modifier is not None
            else 0
        ),
        also_modify_current_hit_points=(
            maximum_hit_point_modifier.also_modify_current
            if maximum_hit_point_modifier is not None
            else False
        ),
        slot_maximum_hit_point_increment=(
            slot_scaling_value(raw, "hit_point_maximum", int) or 0
        ),
        damage_resistances=damage_resistances,
        damage_resistance_choice=damage_resistance_choice,
        condition_save_advantages=condition_save_advantages,
        roll_modifiers=roll_modifiers,
        recast_ends_previous=raw.capability.recast_ends_previous,
        armor_class_modifier=armor_class_modifier,
        speed_modifier_feet=(speed_modifier.feet if speed_modifier is not None else 0),
        speed_modifier_duration_rounds=(
            effect_duration_rounds(speed_modifier.duration)
            if speed_modifier is not None
            else None
        ),
        damage_reduction_types=(
            tuple(damage_reduction.damage_types) if damage_reduction is not None else ()
        ),
        damage_reduction_choice=(
            damage_reduction is not None and damage_reduction.selection == "choose_one"
        ),
        damage_reduction_dice=(
            damage_reduction.dice if damage_reduction is not None else None
        ),
        condition_immunities=condition_immunities,
        senses=senses,
        roll_modifier_ability_choices=tuple(
            normalize_save_ability(ability)
            for effect in outcome.effects
            if isinstance(effect.root, RollModifierEffectSchema)
            for ability in effect.root.ability_options
        ),
        definition=compile_definition(target, resolution, outcome),
    )
