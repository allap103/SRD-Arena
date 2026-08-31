"""Group class definitions with their separately authored features."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from srd_arena.content.common.catalog import SourceCatalog
from srd_arena.content.common.schema import SourceModel
from srd_arena.content.common.sources import SOURCE_PRIORITY, load_json

from .schema import ClassFeatureSchema, ClassSchema


@dataclass(frozen=True)
class ClassRecord:
    """Bundle one class definition with the features that belong to it."""

    definition: ClassSchema
    features: tuple[ClassFeatureSchema, ...]


ClassCatalog = SourceCatalog[ClassRecord]


def load_class_catalog(directory: str | Path) -> ClassCatalog:
    """Group each authored class with features matching its name and source.

    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     root = Path(directory)
    ...     fighter = root / "classes" / "fighter"
    ...     fighter.mkdir(parents=True)
    ...     _ = (fighter / "class.json").write_text(
    ...         '{"name": "Fighter", "source": "X"}', encoding="utf-8")
    ...     load_class_catalog(root).find("fighter", None).definition.name
    'Fighter'
    """

    system_dir = Path(directory)
    class_dir = system_dir / "classes"
    definitions = _load_paths(
        class_dir.glob("*/class.json"),
        ClassSchema,
    )
    features = _load_paths(
        class_dir.glob("*/features/*.json"),
        ClassFeatureSchema,
    )
    records = [
        ClassRecord(
            definition=definition,
            features=tuple(
                feature
                for feature in features
                if feature.class_name.casefold() == definition.name.casefold()
                and feature.class_source.casefold() == definition.source.casefold()
            ),
        )
        for definition in definitions
    ]
    return SourceCatalog(
        records,
        name_of=lambda record: record.definition.public_name,
        source_of=lambda record: record.definition.source,
        source_priority=SOURCE_PRIORITY,
    )


def _load_paths[T: SourceModel](paths: Iterable[Path], schema: type[T]) -> list[T]:
    return [schema.model_validate(load_json(path)) for path in sorted(paths)]
