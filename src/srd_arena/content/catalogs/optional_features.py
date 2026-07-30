from pathlib import Path

from srd_arena.content.schemas.optional_features import OptionalFeatureSchema
from srd_arena.content.sources import SOURCE_PRIORITY, load_json
from .base import SourceCatalog

OptionalFeatureCatalog = SourceCatalog[OptionalFeatureSchema]


def load_optional_feature_catalog(directory: str | Path) -> OptionalFeatureCatalog:
    system_dir = Path(directory)
    features_dir = system_dir / "optional_features"
    records = [
        OptionalFeatureSchema.model_validate(load_json(path))
        for path in sorted(features_dir.glob("*.json"))
    ]
    return SourceCatalog(
        records,
        name_of=lambda feature: feature.public_name,
        source_of=lambda feature: feature.source,
        source_priority=SOURCE_PRIORITY,
    )
