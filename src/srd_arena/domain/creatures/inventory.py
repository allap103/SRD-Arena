from dataclasses import dataclass, field


@dataclass
class Inventory:
    items: list[str] = field(default_factory=list)

    def add_item(self, item: str) -> None:
        self.items.append(item)

    def remove_item(self, item: str) -> bool:
        if item in self.items:
            self.items.remove(item)
            return True
        return False

    def remove_items(self, item: str, quantity: int) -> int:
        removed = 0
        for _ in range(quantity):
            if self.remove_item(item):
                removed += 1
        return removed

    def has_item(self, item: str) -> bool:
        return item in self.items

    def count_item(self, item: str) -> int:
        return self.items.count(item)
