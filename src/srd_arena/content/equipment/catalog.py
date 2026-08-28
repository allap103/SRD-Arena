"""Discover and index authored equipment by name and source."""

from pathlib import Path

from srd_arena.content.common.catalog import SourceCatalog
from srd_arena.content.common.sources import SOURCE_PRIORITY, load_json

from .schema import ItemSchema

ItemCatalog = SourceCatalog[ItemSchema]


def load_item_catalog(directory: str | Path) -> ItemCatalog:
    """Validate equipment files and index them by source-aware identity.

    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     root = Path(directory)
    ...     (root / "items").mkdir()
    ...     _ = (root / "items" / "rope.json").write_text(
    ...         '{"name": "Rope", "source": "X"}', encoding="utf-8")
    ...     catalog = load_item_catalog(root)
    ...     catalog.find("rope", None).name
    'Rope'
    """

    system_dir = Path(directory)
    base_items_dir = system_dir / "items_base"
    items_dir = system_dir / "items"
    records = [
        ItemSchema.model_validate(load_json(path))
        for content_dir in (base_items_dir, items_dir)
        for path in sorted(content_dir.glob("*.json"))
    ]

    return SourceCatalog(
        records,
        name_of=lambda item: item.public_name,
        source_of=lambda item: item.source,
        source_priority=SOURCE_PRIORITY,
    )
