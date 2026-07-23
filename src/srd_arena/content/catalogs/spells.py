from pathlib import Path

from srd_arena.content.schemas.spells import SpellFileSchema, SpellSchema
from srd_arena.content.sources import SOURCE_PRIORITY, load_json
from .base import SourceCatalog

SpellCatalog = SourceCatalog[SpellSchema]


def load_spell_catalog(directory: str | Path) -> SpellCatalog:
    spells_dir = Path(directory) / "spells"
    records: list[SpellSchema] = []
    if spells_dir.is_dir():
        for path in sorted(spells_dir.glob("spells-*.json")):
            source_file = SpellFileSchema.model_validate(load_json(path))
            records.extend(source_file.spell)
    return SourceCatalog(
        records,
        name_of=lambda spell: spell.public_name,
        source_of=lambda spell: spell.source,
        source_priority=SOURCE_PRIORITY,
    )
