"""Describe alternative intrinsic Armor Class calculations."""

from __future__ import annotations

from dataclasses import dataclass

from .attributes import Attributes

ABILITY_NAMES = frozenset(
    {
        "strength",
        "dexterity",
        "constitution",
        "wisdom",
        "intelligence",
        "charisma",
    }
)


@dataclass(frozen=True)
class ArmorClassCalculation:
    """Calculate one non-stacking candidate for a creature's intrinsic AC.

    Armor formulas compete with the creature's normal armor calculation; their
    components are not bonuses and therefore must not be added together.

    >>> attributes = Attributes(10, 1, 10, 16, 14, 10, 10, 10, 10)
    >>> ArmorClassCalculation(
    ...     "unarmored_defense", "Unarmored Defense", 10,
    ...     ("dexterity", "constitution"),
    ... ).resolve(attributes)
    15
    """

    id: str
    label: str
    base: int
    ability_modifiers: tuple[str, ...] = ()
    requires_unarmored: bool = False

    def __post_init__(self) -> None:
        unknown = set(self.ability_modifiers) - ABILITY_NAMES
        if unknown:
            raise ValueError(f"Unknown AC calculation abilities: {sorted(unknown)}")

    def resolve(self, attributes: Attributes) -> int:
        """Return this formula's AC candidate for the supplied attributes."""

        scores = {
            "strength": attributes.strength,
            "dexterity": attributes.dexterity,
            "constitution": attributes.constitution,
            "wisdom": attributes.wisdom,
            "intelligence": attributes.intelligence,
            "charisma": attributes.charisma,
        }
        return self.base + sum(
            (scores[ability] - 10) // 2 for ability in self.ability_modifiers
        )
