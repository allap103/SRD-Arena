from dataclasses import dataclass, field

from ..game_logging import CHANNEL_SYSTEM, get_game_logger

LOGGER = get_game_logger(CHANNEL_SYSTEM)


@dataclass
class Inventory:
    items: list[str] = field(default_factory=list)

    def add_item(self, item: str):
        self.items.append(item)

    def remove_item(self, item: str):
        if item in self.items:
            self.items.remove(item)
        else:
            LOGGER.info(f"Item '{item}' not found in inventory.")

    def remove_items(self, item: str, quantity: int):
        for _ in range(quantity):
            self.remove_item(item)

    def has_item(self, item: str) -> bool:
        return item in self.items

    def count_item(self, item: str) -> int:
        return self.items.count(item)
