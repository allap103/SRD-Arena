"""Build domain spells from authored spell schemas."""

from srd_arena.content.capabilities import build_capability
from srd_arena.content.common.sources import slug
import srd_arena.domain.capabilities as capability_domain
from srd_arena.domain.spells import Spell
from .schema import SpellSchema
from .metadata import (
    remove_effect_selection,
    spell_area_size_feet,
    spell_damage_dice,
    spell_geometry_mode,
    spell_removable_conditions,
    spell_removable_effect_kinds,
)


def build_spell(spell_schema: SpellSchema) -> Spell:
    """Build a domain spell from validated authored content."""
    definition = build_spell_definition(spell_schema)
    return Spell(
        id=slug(spell_schema.public_name),
        name=spell_schema.public_name,
        source=spell_schema.source,
        level=spell_schema.level,
        school=spell_schema.school,
        casting_time=tuple(spell_schema.time),
        range_data=dict(spell_schema.range),
        duration_data=tuple(spell_schema.duration),
        components=dict(spell_schema.components),
        saving_throw_abilities=tuple(
            normalize_save_ability(value) for value in spell_schema.saving_throw
        ),
        condition_inflict=tuple(spell_schema.condition_inflict),
        removable_conditions=spell_removable_conditions(spell_schema),
        removable_effect_kinds=spell_removable_effect_kinds(spell_schema),
        remove_effect_selection=remove_effect_selection(spell_schema),
        damage_dice=spell_damage_dice(spell_schema),
        damage_inflict=tuple(spell_schema.damage_inflict),
        area_tags=tuple(spell_schema.area_tags),
        geometry_mode=spell_geometry_mode(spell_schema),
        area_size_feet=spell_area_size_feet(spell_schema),
        concentration=any(
            bool(duration.get("concentration"))
            for duration in spell_schema.duration
            if isinstance(duration, dict)
        ),
        recast_ends_previous=(
            spell_schema.capability.reactivation_ends_previous
            if spell_schema.capability is not None
            else False
        ),
        self_removal_blocked_conditions=(
            tuple(spell_schema.capability.blocked_self_removal_conditions)
            if spell_schema.capability is not None
            else ()
        ),
        target_requirements=target_requirements(spell_schema, definition),
        definition=definition,
        activation=build_activation(spell_schema),
    )


def build_spell_definition(
    spell_schema: SpellSchema,
) -> capability_domain.CapabilityDefinition | None:
    """Build an executable spell through the shared capability builder."""
    if not spell_schema.executable:
        return None
    assert spell_schema.capability is not None
    capability = spell_schema.capability
    return build_capability(
        target=capability.target,
        resolution=capability.resolution,
        content=f"Spell '{spell_schema.public_name}'",
        condition_selection=capability.condition_application,
        scaling_rules=capability.scaling,
        triggers=capability.outcome_triggers,
    )


def build_activation(
    spell_schema: SpellSchema,
) -> capability_domain.CapabilityActivation | None:
    if not spell_schema.time:
        return None
    activation_by_unit: dict[str, capability_domain.CapabilityActivation] = {
        "action": "action",
        "bonus": "bonus_action",
        "reaction": "reaction",
    }
    unit = spell_schema.time[0].get("unit")
    return activation_by_unit.get(unit) if isinstance(unit, str) else None


def target_requirements(
    spell_schema: SpellSchema,
    definition: capability_domain.CapabilityDefinition | None = None,
) -> tuple[capability_domain.CapabilityRequirement, ...]:
    if definition is not None:
        return definition.target.requirements
    creature_types = tuple(spell_schema.affects_creature_type)
    return (
        (capability_domain.CreatureTypeRequirement(creature_types),)
        if creature_types
        else ()
    )


def normalize_save_ability(value: str) -> str:
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
