from pathlib import Path

from .schema import SpellSchema
from srd_arena.content.common.sources import SOURCE_PRIORITY, load_json
from srd_arena.content.common.catalog import SourceCatalog

SpellCatalog = SourceCatalog[SpellSchema]


def load_spell_catalog(directory: str | Path) -> SpellCatalog:
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
