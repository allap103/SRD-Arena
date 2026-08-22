"""Build domain spells from authored spell schemas."""

from .catalog import SpellCatalog
from srd_arena.content.common.sources import slug
from srd_arena.domain.spells import Spell
from .building import (
    build_activation,
    build_spell_definition,
    find_spell,
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


def build_spell(
    name: str,
    source: str | None,
    catalog: SpellCatalog | None,
) -> Spell:
    raw = find_spell(name, source, catalog)
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
        recast_ends_previous=(
            raw.capability.recast_ends_previous if raw.capability is not None else False
        ),
        self_removal_blocked_conditions=(
            tuple(raw.capability.self_removal_blocked_conditions)
            if raw.capability is not None
            else ()
        ),
        target_requirements=target_requirements(raw),
        definition=build_spell_definition(raw),
        activation=build_activation(raw),
    )
