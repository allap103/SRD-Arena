"""Provide equipment support for the creatures package."""

from dataclasses import dataclass, field


@dataclass
class Equipment:
    """Represent an equipment."""

    equipped_items: dict[str, str | None] = field(
        default_factory=lambda: {
            "head": None,
            "body": None,
            "legs": None,
            "feet": None,
            "hands": None,
            "right_hand": None,
            "left_hand": None,
            "accessory": None,
        }
    )

    def equip(self, item: str, slot: str) -> bool:
        """Equip an item, replacing anything currently occupying the slot.

        >>> equipment = Equipment()
        >>> equipment.equip("longsword", "right_hand")
        True
        >>> equipment.show()["right_hand"]
        'longsword'
        >>> equipment.equip("helmet", "unknown")
        False
        """
        if slot not in self.equipped_items:
            return False
        if self.equipped_items[slot] is not None:
            self.unequip(slot)
        self.equipped_items[slot] = item
        return True

    def unequip(self, slot: str) -> str | None:
        """Clear a slot and return the removed item, if any.

        >>> equipment = Equipment()
        >>> equipment.equip("shield", "left_hand")
        True
        >>> equipment.unequip("left_hand")
        'shield'
        >>> equipment.unequip("left_hand") is None
        True
        """
        if slot not in self.equipped_items:
            return None
        if self.equipped_items[slot] is not None:
            removed_item = self.equipped_items[slot]
            self.equipped_items[slot] = None
            return removed_item
        return None

    def show(self) -> dict[str, str | None]:
        """Return a copy of the equipment-slot mapping.

        >>> equipment = Equipment()
        >>> snapshot = equipment.show()
        >>> snapshot["head"] = "helmet"
        >>> equipment.show()["head"] is None
        True
        """
        return dict(self.equipped_items)

    def is_equipped(self, item: str) -> bool:
        """Return whether an item occupies any equipment slot.

        >>> equipment = Equipment()
        >>> equipment.equip("shield", "left_hand")
        True
        >>> equipment.is_equipped("shield")
        True
        """
        return item in self.equipped_items.values()
