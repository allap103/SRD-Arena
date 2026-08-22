from collections.abc import Sequence

from srd_arena.content.spells.catalog import SpellCatalog
from srd_arena.content.spells.schema import SpellSchema
from srd_arena.domain.capabilities import CreatureTypeRequirement


def find_spell(
    name: str, source: str | None, catalog: SpellCatalog | None
) -> SpellSchema:
    if catalog is None:
        raise ValueError(
            f"Creature references spell '{name}', but no spell catalog was loaded."
        )
    return catalog.find(name, source)


def creature_types_from_requirements(
    requirements: Sequence[object],
) -> tuple[str, ...]:
    return tuple(
        creature_type
        for requirement in requirements
        if getattr(requirement, "type", None) == "creature_type"
        for creature_type in getattr(requirement, "creature_types", ())
    )


def target_requirements(raw: SpellSchema) -> tuple[CreatureTypeRequirement, ...]:
    creature_types = tuple(raw.affects_creature_type)
    if raw.capability is not None and raw.capability.target.type == "creature":
        capability_types = creature_types_from_requirements(
            raw.capability.target.requirements
        )
        if capability_types:
            creature_types = capability_types
    return (CreatureTypeRequirement(creature_types),) if creature_types else ()


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
