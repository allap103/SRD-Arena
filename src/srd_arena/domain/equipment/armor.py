"""Define the combat statistics supplied by worn armor and shields."""

from dataclasses import dataclass
from typing import Literal

ArmorCategory = Literal["light", "medium", "heavy", "shield"]


@dataclass(frozen=True)
class ArmorStat:
    """Describe an armor item's AC formula and secondary restrictions.

    ``armor_class`` is a base value for armor suits and a bonus for shields.
    The category determines how much of the wearer's Dexterity modifier a suit
    adds to that base value.

    >>> ArmorStat("medium", 14).resolve_armor_class(3)
    16
    >>> ArmorStat("heavy", 16).resolve_armor_class(-1)
    16
    """

    category: ArmorCategory
    armor_class: int
    strength_requirement: int | None = None
    stealth_disadvantage: bool = False

    def resolve_armor_class(self, dexterity_modifier: int) -> int:
        """Return the suit's AC after applying its category's Dexterity rule."""

        if self.category == "light":
            return self.armor_class + dexterity_modifier
        if self.category == "medium":
            return self.armor_class + min(dexterity_modifier, 2)
        return self.armor_class
