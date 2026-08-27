"""Index optional class features independently of a creature build."""

from pathlib import Path

from srd_arena.content.common.catalog import SourceCatalog
from srd_arena.content.common.sources import SOURCE_PRIORITY, load_json

from .optional_feature_schema import OptionalFeatureSchema

OptionalFeatureCatalog = SourceCatalog[OptionalFeatureSchema]


def load_optional_feature_catalog(directory: str | Path) -> OptionalFeatureCatalog:
    """Validate and index optional class features from a system directory.

    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     root = Path(directory)
    ...     (root / "optional_features").mkdir()
    ...     _ = (root / "optional_features" / "style.json").write_text(
    ...         '{"name": "Defense", "source": "X"}', encoding="utf-8")
    ...     load_optional_feature_catalog(root).find("defense", None).name
    'Defense'
    """

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
