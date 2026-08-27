"""Provide items support for the equipment package."""

from dataclasses import dataclass

from .armor import ArmorStat
from .weapons import WeaponStat


@dataclass
class Item:
    """Represent an item."""

    id: str
    name: str
    description: str
    category: str
    weapon_stat: WeaponStat | None = None
    armor_stat: ArmorStat | None = None
    item_type: str = ""
    misc_tags: list[str] | None = None

    def has_misc_tag(self, tag: str) -> bool:
        """Return whether the item carries a miscellaneous rules tag.

        >>> torch = Item("torch", "Torch", "", "gear", misc_tags=["light"])
        >>> torch.has_misc_tag("light")
        True
        >>> torch.has_misc_tag("heavy")
        False
        """
        return tag in (self.misc_tags or [])
