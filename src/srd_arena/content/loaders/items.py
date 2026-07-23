from pathlib import Path

from ...domain.equipment import Item
from ..catalogs import load_item_catalog
from ..sources import SOURCE_PRIORITY
from ..translators import build_item


def load_system_items(directory: str | Path) -> list[Item]:
    items_by_id: dict[str, tuple[int, Item]] = {}
    for source_item in load_item_catalog(directory):
        item = build_item(source_item)
        priority = SOURCE_PRIORITY.get(source_item.source, 0)
        current = items_by_id.get(item.id)
        if current is None or priority >= current[0]:
            items_by_id[item.id] = (priority, item)
    return [item for _, item in items_by_id.values()]
