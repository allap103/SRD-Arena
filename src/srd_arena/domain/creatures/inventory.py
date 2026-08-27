"""Provide inventory support for the creatures package."""

from dataclasses import dataclass, field


@dataclass
class Inventory:
    """Represent an inventory."""

    items: list[str] = field(default_factory=list)

    def add_item(self, item: str) -> None:
        """Add one item identifier to the inventory.

        >>> inventory = Inventory()
        >>> inventory.add_item("rope")
        >>> inventory.items
        ['rope']
        """
        self.items.append(item)

    def remove_item(self, item: str) -> bool:
        """Remove one matching item and report whether it existed.

        >>> inventory = Inventory(["rope", "torch"])
        >>> inventory.remove_item("rope")
        True
        >>> inventory.remove_item("rope")
        False
        """
        if item in self.items:
            self.items.remove(item)
            return True
        return False

    def remove_items(self, item: str, quantity: int) -> int:
        """Remove up to a requested quantity and return the amount removed.

        >>> inventory = Inventory(["torch", "torch"])
        >>> inventory.remove_items("torch", 3)
        2
        """
        removed = 0
        for _ in range(quantity):
            if self.remove_item(item):
                removed += 1
        return removed

    def has_item(self, item: str) -> bool:
        """Return whether at least one matching item is present.

        >>> Inventory(["rope"]).has_item("rope")
        True
        """
        return item in self.items

    def count_item(self, item: str) -> int:
        """Count matching item identifiers.

        >>> Inventory(["torch", "rope", "torch"]).count_item("torch")
        2
        """
        return self.items.count(item)
