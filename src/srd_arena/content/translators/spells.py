from collections.abc import Sequence
import re

from srd_arena.content.catalogs import SpellCatalog
from srd_arena.content.schemas.spells import SpellSchema
from srd_arena.content.schemas.action_mechanics import (
    ConditionEffectSchema,
    DamageEffectSchema,
)
from srd_arena.content.schemas.spell_mechanics import (
    AutomaticResolutionSchema,
    ConditionImmunityRequirementSchema,
    CreatureTraitRequirementSchema,
    SavingThrowResolutionSchema,
    SpellAttackResolutionSchema,
)
from srd_arena.content.sources import slug
from srd_arena.domain.spells import ImmediateSpellMechanics, Spell, SpellDamage
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
            _normalize_save_ability(value)
            for value in raw.saving_throw
        ),
        condition_inflict=tuple(raw.condition_inflict),
        removable_conditions=_spell_removable_conditions(raw),
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
    resolution = raw.mechanics.resolution.root
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
    geometry = target.geometry if target.type == "area" else None
    return ImmediateSpellMechanics(
        resolution=resolution.type,
        target=target.type,
        damage=damage,
        save_ability=(
            _normalize_save_ability(resolution.ability)
            if isinstance(resolution, SavingThrowResolutionSchema)
            and resolution.ability is not None
            else raw.saving_throw[0] if raw.saving_throw else None
        ),
        attack_mode=(
            resolution.mode if isinstance(resolution, SpellAttackResolutionSchema) else None
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
        slot_damage_increment=_slot_damage_increment(raw),
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
        target_disposition=(
            target.disposition if target.type == "creature" else "any"
        ),
        repeat_failure_conditions=_repeat_failure_conditions(resolution),
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
            target.count.maximum
            if target.type == "creature" and isinstance(target.count.maximum, int)
            else 1
        ),
        slot_target_increment=_slot_target_increment(raw),
        choose_area_targets=(
            target.type == "area" and target.occupants == "chosen"
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


def _slot_damage_increment(raw: SpellSchema) -> str | None:
    assert raw.mechanics is not None
    for scaling in raw.mechanics.scaling:
        for increment in scaling.per_level:
            if increment.type == "damage_dice" and isinstance(increment.amount, str):
                return increment.amount
    return None


def _slot_target_increment(raw: SpellSchema) -> int:
    assert raw.mechanics is not None
    return sum(
        increment.amount
        for scaling in raw.mechanics.scaling
        for increment in scaling.per_level
        if increment.type == "target_count"
        and isinstance(increment.amount, int)
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
            and getattr(requirement, "relationship", None)
            == "fighting_source_team"
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
    return (
        (CreatureTypeRequirement(creature_types),)
        if creature_types
        else ()
    )


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
    for entry in raw.entries:
        if not isinstance(entry, str):
            continue
        match = re.search(r"\{@damage ([^}]+)\}", entry)
        if match is not None:
            return match.group(1)
    return None


def _spell_removable_conditions(raw: SpellSchema) -> tuple[str, ...]:
    text_parts = [entry for entry in raw.entries if isinstance(entry, str)]
    if not text_parts:
        return ()
    text = " ".join(text_parts)
    if "end one condition on it:" not in text.casefold():
        return ()
    return tuple(
        match.casefold()
        for match in re.findall(r"\{@condition ([^|}]+)", text)
    )


def _spell_geometry_mode(raw: SpellSchema) -> str:
    if raw.mechanics is not None and raw.mechanics.target.type == "area":
        return (
            "directional_area"
            if raw.mechanics.target.origin == "self"
            else "point_area"
        )
    range_type = (
        raw.range.get("type")
        if isinstance(raw.range.get("type"), str)
        else None
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
