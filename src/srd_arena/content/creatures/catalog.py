"""Discover and index validated monster definitions from the bestiary."""

from pathlib import Path

from srd_arena.content.common.catalog import SourceCatalog
from srd_arena.content.common.sources import SOURCE_PRIORITY, load_json

from .stat_block_schema import BestiaryMonsterSchema

BestiaryCatalog = SourceCatalog[BestiaryMonsterSchema]


def load_bestiary_catalog(directory: str | Path) -> BestiaryCatalog:
    """Validate monster files and index them by source-aware content identity.

    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     root = Path(directory)
    ...     monsters = root / "monsters"
    ...     monsters.mkdir()
    ...     _ = (monsters / "goblin.json").write_text(
    ...         '{"name": "Goblin", "source": "XMM"}'
    ...     )
    ...     catalog = load_bestiary_catalog(root)
    >>> catalog.find("goblin", "xmm").public_name
    'Goblin'
    """

    system_dir = Path(directory)
    monsters_dir = system_dir / "monsters"
    records = [
        BestiaryMonsterSchema.model_validate(load_json(path))
        for path in sorted(monsters_dir.glob("*.json"))
    ]
    return SourceCatalog(
        records,
        name_of=lambda monster: monster.public_name,
        source_of=lambda monster: monster.source,
        source_priority=SOURCE_PRIORITY,
    )
