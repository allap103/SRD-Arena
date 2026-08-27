"""Group class and subclass definitions with their separately authored features."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from srd_arena.content.common.catalog import SourceCatalog
from srd_arena.content.common.schema import SourceModel
from srd_arena.content.common.sources import SOURCE_PRIORITY, load_json

from .schema import (
    ClassFeatureSchema,
    ClassSchema,
    SubclassFeatureSchema,
    SubclassSchema,
)


@dataclass(frozen=True)
class ClassRecord:
    """Bundle one class definition with the features that belong to it."""

    definition: ClassSchema
    features: tuple[ClassFeatureSchema, ...]


@dataclass(frozen=True)
class SubclassRecord:
    """Bundle one subclass definition with the features that belong to it."""

    definition: SubclassSchema
    features: tuple[SubclassFeatureSchema, ...]


ClassCatalog = SourceCatalog[ClassRecord]


class SubclassCatalog:
    """Resolve subclasses using both their own and their parent class identities."""

    def __init__(self, records: list[SubclassRecord]) -> None:
        self._records = records
        self._by_identity = {
            (
                record.definition.public_name.casefold(),
                record.definition.source.casefold(),
                record.definition.class_name.casefold(),
                record.definition.class_source.casefold(),
            ): record
            for record in records
        }
        if len(self._by_identity) != len(records):
            raise ValueError("Duplicate subclass content identity.")

    def find(
        self,
        name: str,
        source: str | None,
        class_name: str,
        class_source: str | None,
    ) -> SubclassRecord:
        """Find a subclass by its own and its parent class identities.

        >>> champion = SubclassSchema(name="Champion", source="X",
        ...     className="Fighter", classSource="X")
        >>> catalog = SubclassCatalog([SubclassRecord(champion, ())])
        >>> catalog.find("champion", None, "fighter", None).definition.name
        'Champion'
        """
        name_key = name.casefold()
        class_name_key = class_name.casefold()
        candidates = [
            record
            for record in self._records
            if record.definition.public_name.casefold() == name_key
            and record.definition.class_name.casefold() == class_name_key
            and (
                source is None
                or record.definition.source.casefold() == source.casefold()
            )
            and (
                class_source is None
                or record.definition.class_source.casefold() == class_source.casefold()
            )
        ]
        if not candidates:
            source_text = f"|{source}" if source else ""
            raise KeyError(f"Subclass '{name}{source_text}' not found.")
        return max(
            candidates,
            key=lambda record: SOURCE_PRIORITY.get(record.definition.source, 0),
        )

    def __len__(self) -> int:
        return len(self._records)


def load_class_catalog(directory: str | Path) -> ClassCatalog:
    """Group each authored class with features matching its name and source."""

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


def load_subclass_catalog(directory: str | Path) -> SubclassCatalog:
    """Group each subclass with features matching it and its parent class."""

    system_dir = Path(directory)
    definitions = _load_records(system_dir / "subclasses", SubclassSchema)
    features = _load_records(
        system_dir / "subclass_features",
        SubclassFeatureSchema,
    )
    records = [
        SubclassRecord(
            definition=definition,
            features=tuple(
                feature
                for feature in features
                if feature.class_name.casefold() == definition.class_name.casefold()
                and feature.class_source.casefold()
                == definition.class_source.casefold()
                and feature.subclass_short_name.casefold()
                == (definition.short_name or definition.name).casefold()
                and feature.subclass_source.casefold() == definition.source.casefold()
            ),
        )
        for definition in definitions
    ]
    return SubclassCatalog(records)


def _load_records[T: SourceModel](directory: Path, schema: type[T]) -> list[T]:
    return _load_paths(directory.glob("*.json"), schema)


def _load_paths[T: SourceModel](paths: Iterable[Path], schema: type[T]) -> list[T]:
    return [schema.model_validate(load_json(path)) for path in sorted(paths)]
