from collections.abc import Sequence
import re
from typing import overload

from srd_arena.content.catalogs import SpellCatalog
from srd_arena.content.schemas.spells import SpellSchema
from srd_arena.content.schemas.action_mechanics import (
    ConditionEffectSchema,
    DamageEffectSchema,
)
from srd_arena.content.schemas.spell_mechanics import (
    AutomaticResolutionSchema,
    CasterLevelScalingSchema,
    ConditionImmunityRequirementSchema,
    CreatureTraitRequirementSchema,
    HealingEffectSchema,
    HitPointMaximumModifierEffectSchema,
    RepeatResolutionSchema,
    RemoveEffectSchema,
    SavingThrowResolutionSchema,
    SequenceResolutionSchema,
    SlotScalingSchema,
    SpellAttackResolutionSchema,
    TemporaryHitPointsEffectSchema,
)
from srd_arena.content.sources import slug
from srd_arena.domain.spells import (
    FollowUpSpellResolution,
    ImmediateSpellMechanics,
    Spell,
    SpellDamage,
    SpellHealing,
    SpellTemporaryHitPoints,
)
from srd_arena.domain.creatures import CreatureTypeRequirement


def build_spell(
    name: str,
    source: str | None,
    catalog: SpellCatalog | None,
) -> Spell:
    raw = _find_spell(name, source, catalog)
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
            _normalize_save_ability(value) for value in raw.saving_throw
        ),
        condition_inflict=tuple(raw.condition_inflict),
        removable_conditions=_spell_removable_conditions(raw),
        removable_effect_kinds=_spell_removable_effect_kinds(raw),
        remove_effect_selection=_remove_effect_selection(raw),
        damage_dice=_spell_damage_dice(raw),
        damage_inflict=tuple(raw.damage_inflict),
        area_tags=tuple(raw.area_tags),
        geometry_mode=_spell_geometry_mode(raw),
        area_size_feet=_spell_area_size_feet(raw),
        concentration=any(
            bool(duration.get("concentration"))
            for duration in raw.duration
            if isinstance(duration, dict)
        ),
        target_requirements=_target_requirements(raw),
        mechanics=_immediate_mechanics(raw),
    )


def _immediate_mechanics(raw: SpellSchema) -> ImmediateSpellMechanics | None:
    if raw.mechanics is None:
        return None
    target = raw.mechanics.target
    outer_resolution = raw.mechanics.resolution.root
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
    geometry = target.geometry if target.type == "area" else None
    return ImmediateSpellMechanics(
        resolution=resolution.type,
        target=target.type,
        damage=damage,
        save_ability=(
            _normalize_save_ability(resolution.ability)
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
            _creature_types_from_requirements(resolution.automatic_failure)
            if isinstance(resolution, SavingThrowResolutionSchema)
            else ()
        ),
        disadvantage_creature_types=(
            tuple(
                creature_type
                for modifier in resolution.save_modifiers
                if modifier.mode == "disadvantage"
                for creature_type in _creature_types_from_requirements(
                    modifier.requirements
                )
            )
            if isinstance(resolution, SavingThrowResolutionSchema)
            else ()
        ),
        cantrip_damage_by_level=_cantrip_damage_by_level(raw),
        slot_damage_increment=_slot_damage_increment(
            raw,
            damage_types={damage.damage_type for damage in damage},
        ),
        conditions=conditions,
        condition_choice=raw.mechanics.condition_application == "choose_one",
        duration_rounds=_spell_duration_rounds(raw),
        concentration=any(
            bool(duration.get("concentration"))
            for duration in raw.duration
            if isinstance(duration, dict)
        ),
        repeat_save_trigger=_repeat_save_trigger(resolution),
        expires_on_source_turn_end=any(
            isinstance(effect.root, ConditionEffectSchema)
            and effect.root.duration is not None
            and effect.root.duration.type == "end_of_turn"
            and effect.root.duration.creature == "source"
            for effect in outcome.effects
        ),
        target_disposition=(target.disposition if target.type == "creature" else "any"),
        repeat_failure_conditions=_repeat_failure_conditions(resolution),
        repeat_failure_damage=_repeat_failure_damage(resolution),
        end_events=_end_events(raw),
        damage_repeat_save_advantage=_damage_repeat_save_advantage(raw),
        save_advantage_against_opponents=(
            _save_advantage_against_opponents(resolution)
        ),
        automatic_success_condition_immunities=(
            _automatic_success_condition_immunities(resolution)
        ),
        automatic_success_traits=_automatic_success_traits(resolution),
        self_removal_blocked_conditions=tuple(
            raw.mechanics.self_removal_blocked_conditions
        ),
        base_target_count=(
            _target_count_by_caster_level(raw)[0][1]
            if _target_count_by_caster_level(raw)
            else repeated.count
            if repeated is not None and isinstance(repeated.count, int)
            else target.count.maximum
            if target.type == "creature" and isinstance(target.count.maximum, int)
            else 1
        ),
        slot_target_increment=_slot_target_increment(raw),
        choose_area_targets=(target.type == "area" and target.occupants == "chosen"),
        repeat_target_allocations=(
            repeated is not None
            and repeated.allocation in {"same_target", "same_or_different"}
        ),
        require_full_target_count=repeated is not None,
        target_count_by_caster_level=_target_count_by_caster_level(raw),
        follow_up_resolutions=(
            tuple(
                _follow_up_resolution(raw, step)
                for step in sequence.steps[1:]
            )
            if sequence is not None
            else ()
        ),
        healing=healing,
        temporary_hit_points=temporary_hit_points,
        slot_healing_dice_increment=_slot_scaling_value(raw, "healing_dice", str),
        slot_healing_bonus_increment=(
            _slot_scaling_value(raw, "healing_bonus", int) or 0
        ),
        slot_temporary_hit_points_increment=(
            _slot_scaling_value(raw, "temporary_hit_points", int) or 0
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
            _slot_scaling_value(raw, "hit_point_maximum", int) or 0
        ),
    )


@overload
def _slot_scaling_value(
    raw: SpellSchema,
    kind: str,
    value_type: type[str],
) -> str | None: ...


@overload
def _slot_scaling_value(
    raw: SpellSchema,
    kind: str,
    value_type: type[int],
) -> int | None: ...


def _slot_scaling_value(
    raw: SpellSchema,
    kind: str,
    value_type: type[str] | type[int],
) -> str | int | None:
    assert raw.mechanics is not None
    return next(
        (
            increment.amount
            for scaling in raw.mechanics.scaling
            if isinstance(scaling, SlotScalingSchema)
            for increment in scaling.per_level
            if increment.type == kind and isinstance(increment.amount, value_type)
        ),
        None,
    )


def _follow_up_resolution(
    raw: SpellSchema,
    step: object,
) -> FollowUpSpellResolution:
    target = getattr(step, "target", None)
    resolution_wrapper = getattr(step, "resolution", None)
    resolution = getattr(resolution_wrapper, "root", None)
    if target is None or target.type != "area" or target.origin != "target":
        raise ValueError("Follow-up spell resolutions require a target-origin area.")
    if not isinstance(resolution, SavingThrowResolutionSchema):
        raise ValueError("Only saving-throw follow-up resolutions are executable.")
    damage = tuple(
        SpellDamage(effect.root.dice, effect.root.damage_type)
        for effect in resolution.failure.effects
        if isinstance(effect.root, DamageEffectSchema)
    )
    return FollowUpSpellResolution(
        resolution=resolution.type,
        target=target.type,
        damage=damage,
        save_ability=(
            _normalize_save_ability(resolution.ability)
            if resolution.ability is not None
            else None
        ),
        half_damage_on_save=resolution.success_damage == "half",
        area_radius_feet=target.geometry.radius_feet,
        slot_damage_increment=_slot_damage_increment(
            raw,
            damage_types={entry.damage_type for entry in damage},
        ),
    )


def _creature_types_from_requirements(
    requirements: Sequence[object],
) -> tuple[str, ...]:
    return tuple(
        creature_type
        for requirement in requirements
        if getattr(requirement, "type", None) == "creature_type"
        for creature_type in getattr(requirement, "creature_types", ())
    )


def _cantrip_damage_by_level(raw: SpellSchema) -> tuple[tuple[int, str], ...]:
    scaling_data = (raw.model_extra or {}).get("scalingLevelDice")
    if not isinstance(scaling_data, dict):
        return ()
    scaling = scaling_data.get("scaling")
    if not isinstance(scaling, dict):
        return ()
    return tuple(
        sorted(
            (int(level), dice)
            for level, dice in scaling.items()
            if isinstance(level, str) and level.isdigit() and isinstance(dice, str)
        )
    )


def _slot_damage_increment(
    raw: SpellSchema,
    *,
    damage_types: set[str],
) -> str | None:
    assert raw.mechanics is not None
    for scaling in raw.mechanics.scaling:
        if not isinstance(scaling, SlotScalingSchema):
            continue
        for increment in scaling.per_level:
            if (
                increment.type == "damage_dice"
                and isinstance(increment.amount, str)
                and (
                    increment.damage_type is None
                    or increment.damage_type in damage_types
                )
            ):
                return increment.amount
    return None


def _slot_target_increment(raw: SpellSchema) -> int:
    assert raw.mechanics is not None
    return sum(
        increment.amount
        for scaling in raw.mechanics.scaling
        if isinstance(scaling, SlotScalingSchema)
        for increment in scaling.per_level
        if increment.type in {"target_count", "projectile_count"}
        and isinstance(increment.amount, int)
    )


def _target_count_by_caster_level(raw: SpellSchema) -> tuple[tuple[int, int], ...]:
    assert raw.mechanics is not None
    return tuple(
        (threshold.minimum_level, threshold.projectile_count)
        for scaling in raw.mechanics.scaling
        if isinstance(scaling, CasterLevelScalingSchema)
        for threshold in scaling.thresholds
    )


def _spell_duration_rounds(raw: SpellSchema) -> int | None:
    unit_rounds = {"round": 1, "minute": 10, "hour": 600, "day": 14400}
    for entry in raw.duration:
        duration = entry.get("duration")
        if not isinstance(duration, dict):
            continue
        unit = duration.get("type")
        amount = duration.get("amount")
        if isinstance(unit, str) and isinstance(amount, int) and unit in unit_rounds:
            return amount * unit_rounds[unit]
    return None


def _repeat_save_trigger(resolution: object) -> str | None:
    if not isinstance(resolution, SavingThrowResolutionSchema):
        return None
    if resolution.repeat_save is None:
        return None
    aliases = {"turn_end": "end_of_turn", "turn_start": "start_of_turn"}
    return aliases.get(resolution.repeat_save.trigger, resolution.repeat_save.trigger)


def _repeat_failure_conditions(resolution: object) -> tuple[str, ...]:
    if not isinstance(resolution, SavingThrowResolutionSchema):
        return ()
    repeat = resolution.repeat_save
    if repeat is None or repeat.on_failure is None:
        return ()
    failure = repeat.on_failure.root
    if not isinstance(failure, AutomaticResolutionSchema):
        return ()
    return tuple(
        effect.root.condition
        for effect in failure.outcome.effects
        if isinstance(effect.root, ConditionEffectSchema)
    )


def _repeat_failure_damage(resolution: object) -> tuple[SpellDamage, ...]:
    if not isinstance(resolution, SavingThrowResolutionSchema):
        return ()
    repeat = resolution.repeat_save
    if repeat is None or repeat.on_failure is None:
        return ()
    failure = repeat.on_failure.root
    if not isinstance(failure, AutomaticResolutionSchema):
        return ()
    return tuple(
        SpellDamage(effect.root.dice, effect.root.damage_type)
        for effect in failure.outcome.effects
        if isinstance(effect.root, DamageEffectSchema)
    )


def _end_events(raw: SpellSchema) -> tuple[tuple[str, str], ...]:
    if raw.mechanics is None:
        return ()
    events: list[tuple[str, str]] = []
    for trigger in raw.mechanics.outcome_triggers:
        resolution = trigger.resolution.root
        if not isinstance(resolution, AutomaticResolutionSchema):
            continue
        if not resolution.outcome.end_spell:
            continue
        scope = "any"
        for requirement in trigger.requirements:
            if (
                getattr(requirement, "type", None) == "relationship"
                and getattr(requirement, "relationship", None) == "ally_of_source"
            ):
                scope = "source_team"
        events.append((trigger.event, scope))
    return tuple(events)


def _damage_repeat_save_advantage(raw: SpellSchema) -> bool:
    if raw.mechanics is None:
        return False
    return any(
        trigger.event == "target_damaged"
        and isinstance(trigger.resolution.root, SavingThrowResolutionSchema)
        and any(
            modifier.mode == "advantage"
            for modifier in trigger.resolution.root.save_modifiers
        )
        for trigger in raw.mechanics.outcome_triggers
    )


def _save_advantage_against_opponents(resolution: object) -> bool:
    if not isinstance(resolution, SavingThrowResolutionSchema):
        return False
    return any(
        modifier.mode == "advantage"
        and any(
            getattr(requirement, "type", None) == "relationship"
            and getattr(requirement, "relationship", None) == "fighting_source_team"
            for requirement in modifier.requirements
        )
        for modifier in resolution.save_modifiers
    )


def _automatic_success_condition_immunities(
    resolution: object,
) -> tuple[str, ...]:
    if not isinstance(resolution, SavingThrowResolutionSchema):
        return ()
    return tuple(
        requirement.condition
        for requirement in resolution.automatic_success
        if isinstance(requirement, ConditionImmunityRequirementSchema)
    )


def _automatic_success_traits(resolution: object) -> tuple[str, ...]:
    if not isinstance(resolution, SavingThrowResolutionSchema):
        return ()
    return tuple(
        requirement.trait
        for requirement in resolution.automatic_success
        if isinstance(requirement, CreatureTraitRequirementSchema)
    )


def _find_spell(
    name: str,
    source: str | None,
    catalog: SpellCatalog | None,
) -> SpellSchema:
    if catalog is None:
        raise ValueError(
            f"Creature references spell '{name}', but no spell catalog was loaded."
        )
    return catalog.find(name, source)


def _target_requirements(raw: SpellSchema) -> tuple[CreatureTypeRequirement, ...]:
    creature_types = tuple(raw.affects_creature_type)
    if raw.mechanics is not None and raw.mechanics.target.type == "creature":
        mechanics_types = _creature_types_from_requirements(
            raw.mechanics.target.requirements
        )
        if mechanics_types:
            creature_types = mechanics_types
    return (CreatureTypeRequirement(creature_types),) if creature_types else ()


def _normalize_save_ability(value: str) -> str:
    aliases = {
        "str": "strength",
        "dex": "dexterity",
        "con": "constitution",
        "int": "intelligence",
        "wis": "wisdom",
        "cha": "charisma",
    }
    normalized = value.casefold()
    return aliases.get(normalized, normalized)


def _spell_damage_dice(raw: SpellSchema) -> str | None:
    if raw.mechanics is not None:
        resolution = raw.mechanics.resolution.root
        if isinstance(resolution, RepeatResolutionSchema):
            resolution = resolution.resolution.root
        outcome = (
            resolution.failure
            if isinstance(resolution, SavingThrowResolutionSchema)
            else resolution.hit
            if isinstance(resolution, SpellAttackResolutionSchema)
            else resolution.outcome
            if isinstance(resolution, AutomaticResolutionSchema)
            else None
        )
        if outcome is not None:
            damage = next(
                (
                    effect.root
                    for effect in outcome.effects
                    if isinstance(effect.root, DamageEffectSchema)
                ),
                None,
            )
            if damage is not None:
                return damage.dice
    for entry in raw.entries:
        if not isinstance(entry, str):
            continue
        match = re.search(r"\{@damage ([^}]+)\}", entry)
        if match is not None:
            return match.group(1)
    return None


def _spell_removable_conditions(raw: SpellSchema) -> tuple[str, ...]:
    if raw.mechanics is not None:
        resolution = raw.mechanics.resolution.root
        if isinstance(resolution, RepeatResolutionSchema):
            resolution = resolution.resolution.root
        if isinstance(resolution, AutomaticResolutionSchema):
            conditions = tuple(
                condition
                for effect in resolution.outcome.effects
                if isinstance(effect.root, RemoveEffectSchema)
                and "condition" in effect.root.removable
                for condition in effect.root.conditions
            )
            if conditions:
                return conditions
    text_parts = [entry for entry in raw.entries if isinstance(entry, str)]
    if not text_parts:
        return ()
    text = " ".join(text_parts)
    if "end one condition on it:" not in text.casefold():
        return ()
    return tuple(
        match.casefold() for match in re.findall(r"\{@condition ([^|}]+)", text)
    )


def _remove_effect_selection(raw: SpellSchema) -> str | None:
    if raw.mechanics is None:
        return None
    resolution = raw.mechanics.resolution.root
    if isinstance(resolution, RepeatResolutionSchema):
        resolution = resolution.resolution.root
    if not isinstance(resolution, AutomaticResolutionSchema):
        return None
    removal = next(
        (
            effect.root
            for effect in resolution.outcome.effects
            if isinstance(effect.root, RemoveEffectSchema)
        ),
        None,
    )
    return removal.selection if removal is not None else None


def _spell_removable_effect_kinds(raw: SpellSchema) -> tuple[str, ...]:
    if raw.mechanics is None:
        return ()
    resolution = raw.mechanics.resolution.root
    if isinstance(resolution, RepeatResolutionSchema):
        resolution = resolution.resolution.root
    if not isinstance(resolution, AutomaticResolutionSchema):
        return ()
    removal = next(
        (
            effect.root
            for effect in resolution.outcome.effects
            if isinstance(effect.root, RemoveEffectSchema)
        ),
        None,
    )
    return tuple(removal.removable) if removal is not None else ()


def _spell_geometry_mode(raw: SpellSchema) -> str:
    if raw.mechanics is not None and raw.mechanics.target.type == "area":
        return (
            "directional_area"
            if raw.mechanics.target.origin == "self"
            else "point_area"
        )
    range_type = (
        raw.range.get("type") if isinstance(raw.range.get("type"), str) else None
    )
    if _spell_removable_conditions(raw):
        return "point_target"
    if range_type in {"cone", "line", "cube"}:
        return "directional_area"
    if range_type in {"radius", "sphere", "cylinder", "emanation"}:
        return "non_directional_area"
    if range_type == "point" and _spell_area_size_feet(raw) is not None:
        return "point_area"
    return "point_target"


def _spell_area_size_feet(raw: SpellSchema) -> int | None:
    if raw.mechanics is not None and raw.mechanics.target.type == "area":
        geometry = raw.mechanics.target.geometry
        return geometry.radius_feet or geometry.length_feet
    text_parts = [entry for entry in raw.entries if isinstance(entry, str)]
    if not text_parts:
        return None
    radius_match = re.search(r"(\d+)-foot-radius", " ".join(text_parts).casefold())
    return int(radius_match.group(1)) if radius_match is not None else None
