from pathlib import Path

from srd_arena.content.schemas.bestiary import (
    BestiaryFileSchema,
    BestiaryMonsterSchema,
)
from srd_arena.content.sources import SOURCE_PRIORITY, load_json
from .base import SourceCatalog

BestiaryCatalog = SourceCatalog[BestiaryMonsterSchema]


def load_bestiary_catalog(directory: str | Path) -> BestiaryCatalog:
    system_dir = Path(directory)
    records: list[BestiaryMonsterSchema] = []
    for bestiary_dir in (system_dir, system_dir / "bestiary"):
        if not bestiary_dir.is_dir():
            continue
        for path in sorted(bestiary_dir.glob("bestiary-*.json")):
            source_file = BestiaryFileSchema.model_validate(load_json(path))
            records.extend(source_file.monster)
    return SourceCatalog(
        records,
        name_of=lambda monster: monster.public_name,
        source_of=lambda monster: monster.source,
        source_priority=SOURCE_PRIORITY,
    )
