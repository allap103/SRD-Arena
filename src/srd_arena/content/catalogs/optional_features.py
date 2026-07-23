from pathlib import Path

from srd_arena.content.schemas.optional_features import (
    OptionalFeatureFileSchema,
    OptionalFeatureSchema,
)
from srd_arena.content.sources import SOURCE_PRIORITY, load_json
from .base import SourceCatalog

OptionalFeatureCatalog = SourceCatalog[OptionalFeatureSchema]


def load_optional_feature_catalog(directory: str | Path) -> OptionalFeatureCatalog:
    path = Path(directory) / "optionalfeatures.json"
    records: list[OptionalFeatureSchema] = []
    if path.is_file():
        source_file = OptionalFeatureFileSchema.model_validate(load_json(path))
        records.extend(source_file.optional_features)
    return SourceCatalog(
        records,
        name_of=lambda feature: feature.public_name,
        source_of=lambda feature: feature.source,
        source_priority=SOURCE_PRIORITY,
    )
