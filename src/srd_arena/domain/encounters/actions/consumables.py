"""Discover and interpret consumable items that grant encounter actions."""

from __future__ import annotations

import re

from srd_arena.domain.creatures import Creature
from srd_arena.domain.equipment import Item


def healing_potions_in_inventory(
    creature: Creature, items_by_id: dict[str, Item]
) -> list[Item]:
    """Return unique inventory items identified as healing potions.

    >>> from types import SimpleNamespace
    >>> potion = Item(
    ...     "healing_potion", "Potion of Healing", "{@dice 2d4 + 2}", "potion",
    ...     item_type="P", misc_tags=["CNS"],
    ... )
    >>> creature = SimpleNamespace(
    ...     inventory=SimpleNamespace(items=["healing_potion", "healing_potion"])
    ... )
    >>> [item.id for item in healing_potions_in_inventory(
    ...     creature, {"healing_potion": potion}
    ... )]
    ['healing_potion']
    """

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
    """Return the healing dice encoded by a supported potion's rules tags.

    >>> potion = Item(
    ...     "healing_potion", "Potion of Healing", "{@dice 2d4 + 2}", "potion",
    ...     item_type="P", misc_tags=["CNS"],
    ... )
    >>> healing_potion_dice(potion)
    (2, 4, 2)
    """

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
