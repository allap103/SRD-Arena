"""Track item identifiers carried by a creature independently of equipment."""

from dataclasses import dataclass, field


@dataclass
class Inventory:
    """Store carried item identifiers, including repeated consumable items."""

    items: list[str] = field(default_factory=list)

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

    def has_item(self, item: str) -> bool:
        """Return whether at least one matching item is present.

        >>> Inventory(["rope"]).has_item("rope")
        True
        """
        return item in self.items
