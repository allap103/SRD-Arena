"""Provide targeting support for the building package."""

from collections.abc import Sequence

from srd_arena.content.spells.schema import SpellSchema
from srd_arena.domain.capabilities import CreatureTypeRequirement


def creature_types_from_requirements(
    requirements: Sequence[object],
) -> tuple[str, ...]:
    """Handle creature types from requirements."""

    return tuple(
        creature_type
        for requirement in requirements
        if getattr(requirement, "type", None) == "creature_type"
        for creature_type in getattr(requirement, "creature_types", ())
    )


def target_requirements(raw: SpellSchema) -> tuple[CreatureTypeRequirement, ...]:
    """Handle target requirements."""

    creature_types = tuple(raw.affects_creature_type)
    if raw.capability is not None and raw.capability.target.type == "creature":
        capability_types = creature_types_from_requirements(
            raw.capability.target.requirements
        )
        if capability_types:
            creature_types = capability_types
    return (CreatureTypeRequirement(creature_types),) if creature_types else ()


def normalize_save_ability(value: str) -> str:
    """Normalize save ability."""

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
