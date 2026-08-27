"""Translate authored spell targeting into domain target requirements."""

from collections.abc import Sequence

from srd_arena.content.spells.schema import SpellSchema
from srd_arena.domain.capabilities import CreatureTypeRequirement


def creature_types_from_requirements(
    requirements: Sequence[object],
) -> tuple[str, ...]:
    """Extract allowed creature types from authored target requirements.

    >>> from types import SimpleNamespace
    >>> requirements = [SimpleNamespace(
    ...     type="creature_type", creature_types=["humanoid", "giant"])]
    >>> creature_types_from_requirements(requirements)
    ('humanoid', 'giant')
    """

    return tuple(
        creature_type
        for requirement in requirements
        if getattr(requirement, "type", None) == "creature_type"
        for creature_type in getattr(requirement, "creature_types", ())
    )


def target_requirements(raw: SpellSchema) -> tuple[CreatureTypeRequirement, ...]:
    """Build domain eligibility requirements for a spell's selected targets.

    >>> spell = SpellSchema.model_construct(
    ...     affects_creature_type=["humanoid"], capability=None)
    >>> target_requirements(spell)[0].creature_types
    ('humanoid',)
    """

    creature_types = tuple(raw.affects_creature_type)
    if raw.capability is not None and raw.capability.target.type == "creature":
        capability_types = creature_types_from_requirements(
            raw.capability.target.requirements
        )
        if capability_types:
            creature_types = capability_types
    return (CreatureTypeRequirement(creature_types),) if creature_types else ()


def normalize_save_ability(value: str) -> str:
    """Expand an abbreviated authored save ability to its domain name.

    >>> normalize_save_ability("WIS")
    'wisdom'
    >>> normalize_save_ability("constitution")
    'constitution'
    """

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
