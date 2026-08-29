"""Build domain spells from authored spell schemas."""

from srd_arena.content.common.sources import slug
from srd_arena.domain.spells import Spell

from .building import (
    build_activation,
    build_casting_times,
    build_spell_components,
    build_spell_definition,
    build_spell_durations,
    build_spell_range,
    normalize_save_ability,
    target_requirements,
)
from .building.metadata import (
    remove_effect_selection,
    spell_area_size_feet,
    spell_damage_dice,
    spell_geometry_mode,
    spell_removable_conditions,
    spell_removable_effect_kinds,
)
from .schema import SpellSchema


def build_spell(spell_schema: SpellSchema) -> Spell:
    """Build a domain spell from validated authored content.

    Metadata remains available even when a spell has no executable capability.

    >>> schema = SpellSchema(
    ...     name="Light", source="XPHB", level=0, school="E"
    ... )
    >>> spell = build_spell(schema)
    >>> (spell.id, spell.name, spell.definition)
    ('light', 'Light', None)
    """
    return Spell(
        id=slug(spell_schema.public_name),
        name=spell_schema.public_name,
        source=spell_schema.source,
        level=spell_schema.level,
        school=spell_schema.school,
        casting_times=build_casting_times(spell_schema.time),
        range=build_spell_range(spell_schema.range),
        durations=build_spell_durations(spell_schema.duration),
        components=build_spell_components(spell_schema.components),
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
        recast_ends_previous=(
            spell_schema.capability.recast_ends_previous
            if spell_schema.capability is not None
            else False
        ),
        self_removal_blocked_conditions=(
            tuple(spell_schema.capability.self_removal_blocked_conditions)
            if spell_schema.capability is not None
            else ()
        ),
        target_requirements=target_requirements(spell_schema),
        definition=build_spell_definition(spell_schema),
        activation=build_activation(spell_schema),
        resolver_id=spell_schema.implementation.resolver,
    )
