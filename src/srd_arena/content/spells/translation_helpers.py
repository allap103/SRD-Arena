from collections.abc import Sequence
import re
from typing import overload

from .catalog import SpellCatalog
from .schema import SpellSchema
from srd_arena.content.capabilities import (
    ConditionEffectSchema,
    DamageEffectSchema,
)
from .resolution import (
    AutomaticResolutionSchema,
    RepeatResolutionSchema,
    RemoveEffectSchema,
    SavingThrowResolutionSchema,
    SpellAttackResolutionSchema,
)
from .scaling import CasterLevelScalingSchema, SlotScalingSchema
from .targeting import (
    ConditionImmunityRequirementSchema,
    CreatureTraitRequirementSchema,
)
from srd_arena.domain.spells import (
    FollowUpSpellResolution,
    SpellDamage,
)
from srd_arena.domain.capabilities import CreatureTypeRequirement


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
    assert raw.capability is not None
    return next(
        (
            increment.amount
            for scaling in raw.capability.scaling
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
    assert raw.capability is not None
    for scaling in raw.capability.scaling:
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
    assert raw.capability is not None
    return sum(
        increment.amount
        for scaling in raw.capability.scaling
        if isinstance(scaling, SlotScalingSchema)
        for increment in scaling.per_level
        if increment.type in {"target_count", "projectile_count"}
        and isinstance(increment.amount, int)
    )


def _target_count_by_caster_level(raw: SpellSchema) -> tuple[tuple[int, int], ...]:
    assert raw.capability is not None
    return tuple(
        (threshold.minimum_level, threshold.projectile_count)
        for scaling in raw.capability.scaling
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


def _effect_duration_rounds(duration: object) -> int | None:
    if duration is None:
        return None
    duration_type = getattr(duration, "type", None)
    if duration_type in {"start_of_turn", "end_of_turn"}:
        return 1
    if duration_type != "timed":
        return None
    unit_rounds = {"round": 1, "minute": 10, "hour": 600, "day": 14400}
    amount = getattr(duration, "amount", None)
    unit = getattr(duration, "unit", None)
    return (
        amount * unit_rounds[unit]
        if isinstance(amount, int) and isinstance(unit, str) and unit in unit_rounds
        else None
    )


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
    if raw.capability is None:
        return ()
    events: list[tuple[str, str]] = []
    for trigger in raw.capability.outcome_triggers:
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
    if raw.capability is None:
        return False
    return any(
        trigger.event == "target_damaged"
        and isinstance(trigger.resolution.root, SavingThrowResolutionSchema)
        and any(
            modifier.mode == "advantage"
            for modifier in trigger.resolution.root.save_modifiers
        )
        for trigger in raw.capability.outcome_triggers
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
    if raw.capability is not None and raw.capability.target.type == "creature":
        capability_types = _creature_types_from_requirements(
            raw.capability.target.requirements
        )
        if capability_types:
            creature_types = capability_types
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
    if raw.capability is not None:
        resolution = raw.capability.resolution.root
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
    if raw.capability is not None:
        resolution = raw.capability.resolution.root
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
    if raw.capability is None:
        return None
    resolution = raw.capability.resolution.root
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
    if raw.capability is None:
        return ()
    resolution = raw.capability.resolution.root
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
    if raw.capability is not None and raw.capability.target.type == "area":
        return (
            "directional_area"
            if raw.capability.target.origin == "self"
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
    if raw.capability is not None and raw.capability.target.type == "area":
        geometry = raw.capability.target.geometry
        return geometry.radius_feet or geometry.length_feet
    text_parts = [entry for entry in raw.entries if isinstance(entry, str)]
    if not text_parts:
        return None
    radius_match = re.search(r"(\d+)-foot-radius", " ".join(text_parts).casefold())
    return int(radius_match.group(1)) if radius_match is not None else None
