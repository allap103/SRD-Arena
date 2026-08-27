"""Load validated equipment records from system content."""

from pathlib import Path

from srd_arena.content.common.sources import SOURCE_PRIORITY
from srd_arena.domain.equipment import Item

from .builder import build_item
from .catalog import load_item_catalog


def load_system_items(directory: str | Path) -> list[Item]:
    """Build all domain item templates available in a system content directory.

    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     root = Path(directory)
    ...     (root / "items").mkdir()
    ...     _ = (root / "items" / "rope.json").write_text(
    ...         '{"name": "Rope", "source": "X"}', encoding="utf-8")
    ...     [(item.id, item.category) for item in load_system_items(root)]
    [('rope', 'other')]
    """

    items_by_id: dict[str, tuple[int, Item]] = {}
    for source_item in load_item_catalog(directory):
        item = build_item(source_item)
        priority = SOURCE_PRIORITY.get(source_item.source, 0)
        current = items_by_id.get(item.id)
        if current is None or priority >= current[0]:
            items_by_id[item.id] = (priority, item)
    return [item for _, item in items_by_id.values()]
