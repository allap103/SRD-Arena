"""Discover and interpret consumable items that grant encounter actions."""

from __future__ import annotations

import re

from ...creatures import Creature
from ...equipment import Item


def healing_potions_in_inventory(
    creature: Creature, items_by_id: dict[str, Item]
) -> list[Item]:
    """Return inventory items whose tags identify them as healing potions."""

    seen: set[str] = set()
    potions: list[Item] = []
    for item_id in creature.inventory.items:
        if item_id in seen:
            continue
        seen.add(item_id)
        item = items_by_id.get(item_id)
        if item is not None and healing_potion_dice(item) is not None:
            potions.append(item)
    return potions


def healing_potion_dice(item: Item) -> tuple[int, int, int] | None:
    """Return the healing dice encoded by a supported potion's rules tags."""

    if not item.item_type.startswith("P"):
        return None
    if not item.has_misc_tag("CNS"):
        return None
    match = re.search(r"\{@dice\s+(\d+)d(\d+)(?:\s*\+\s*(\d+))?\}", item.description)
    if match is None:
        return None
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )
