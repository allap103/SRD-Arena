from pathlib import Path

from ..schemas.items import BaseItemFileSchema, ItemFileSchema, ItemSchema
from ..sources import SOURCE_PRIORITY, load_json
from .base import SourceCatalog

ItemCatalog = SourceCatalog[ItemSchema]


def load_item_catalog(directory: str | Path) -> ItemCatalog:
    system_dir = Path(directory)
    records: list[ItemSchema] = []

    base_items_path = system_dir / "items-base.json"
    if base_items_path.is_file():
        base_item_file = BaseItemFileSchema.model_validate(load_json(base_items_path))
        records.extend(base_item_file.base_items)

    items_path = system_dir / "items.json"
    if items_path.is_file():
        item_file = ItemFileSchema.model_validate(load_json(items_path))
        records.extend(item_file.items)

    return SourceCatalog(
        records,
        name_of=lambda item: item.public_name,
        source_of=lambda item: item.source,
        source_priority=SOURCE_PRIORITY,
    )
