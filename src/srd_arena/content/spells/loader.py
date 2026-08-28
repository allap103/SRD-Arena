"""Load authored spell records and translate them into domain definitions."""

from pathlib import Path

from srd_arena.content.common.catalog import SourceCatalog
from srd_arena.content.common.sources import SOURCE_PRIORITY, load_json

from .catalog import SpellCatalog
from .schema import SpellSchema


def load_spell_catalog(directory: str | Path) -> SpellCatalog:
    """Load and index validated spell schemas from a system content directory.

    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     root = Path(directory)
    ...     spells = root / "spells"
    ...     spells.mkdir()
    ...     _ = (spells / "light.json").write_text(
    ...         '{"name":"Light","source":"XPHB","level":0,"school":"E"}'
    ...     )
    ...     catalog = load_spell_catalog(root)
    >>> catalog.find("light", "xphb").level
    0
    """
    spells_dir = Path(directory) / "spells"
    records = [
        SpellSchema.model_validate(load_json(path))
        for path in sorted(spells_dir.glob("*.json"))
    ]
    return SourceCatalog(
        records,
        name_of=lambda spell: spell.public_name,
        source_of=lambda spell: spell.source,
        source_priority=SOURCE_PRIORITY,
    )
