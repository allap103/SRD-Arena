from dataclasses import dataclass, field

from ..game_logging import CHANNEL_SYSTEM, get_game_logger

LOGGER = get_game_logger(CHANNEL_SYSTEM)

@dataclass
class Equipment:
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

    def equip(self, item: str, slot: str):
        """
        Equips an item. If the slot is not empty, unequip the currently equipped item first.
         - item: The name of the item to equip.
         - slot: The equipment slot to equip the item in (e.g., 'head', 'body', 'right_hand').
        """
        if slot not in self.equipped_items:
            LOGGER.info(f"Invalid equipment slot '{slot}'.")
            return
        elif self.equipped_items[slot] is not None:
            self.unequip(slot)
        self.equipped_items[slot] = item
        LOGGER.info(f"Equipped '{item}' in slot '{slot}'.")

    def unequip(self, slot: str):
        if slot not in self.equipped_items:
            LOGGER.info(f"Invalid equipment slot '{slot}'.")
            return None
        if self.equipped_items[slot] is not None:
            removed_item = self.equipped_items[slot]
            self.equipped_items[slot] = None
            LOGGER.info(f"Unequipped '{removed_item}' from slot '{slot}'.")
            return removed_item
        else:
            LOGGER.info(f"No item equipped in slot '{slot}' to unequip.")
            return None

    def show(self):
        LOGGER.info("Equipped items:")
        for slot, item in self.equipped_items.items():
            if item is not None:
                LOGGER.info(f"{slot.capitalize()}: {item}")
            else:
                LOGGER.info(f"{slot.capitalize()}: Empty")

    def is_equipped(self, item: str) -> bool:
        return item in self.equipped_items.values()
