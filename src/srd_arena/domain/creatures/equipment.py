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
        """
        Equips an item. If the slot is not empty, unequip the currently equipped item first.
         - item: The name of the item to equip.
         - slot: The equipment slot to equip the item in (e.g., 'head', 'body', 'right_hand').
        """
        if slot not in self.equipped_items:
            return False
        if self.equipped_items[slot] is not None:
            self.unequip(slot)
        self.equipped_items[slot] = item
        return True

    def unequip(self, slot: str) -> str | None:
        if slot not in self.equipped_items:
            return None
        if self.equipped_items[slot] is not None:
            removed_item = self.equipped_items[slot]
            self.equipped_items[slot] = None
            return removed_item
        return None

    def show(self) -> dict[str, str | None]:
        return dict(self.equipped_items)

    def is_equipped(self, item: str) -> bool:
        return item in self.equipped_items.values()
