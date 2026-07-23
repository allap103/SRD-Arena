from dataclasses import dataclass
from pathlib import Path

from srd_arena.content.schemas.classes import (
    ClassFeatureSchema,
    ClassFileSchema,
    ClassSchema,
    SubclassFeatureSchema,
    SubclassSchema,
)
from srd_arena.content.sources import SOURCE_PRIORITY, load_json
from .base import SourceCatalog


@dataclass(frozen=True)
class ClassRecord:
    definition: ClassSchema
    features: tuple[ClassFeatureSchema, ...]


@dataclass(frozen=True)
class SubclassRecord:
    definition: SubclassSchema
    features: tuple[SubclassFeatureSchema, ...]


ClassCatalog = SourceCatalog[ClassRecord]


class SubclassCatalog:
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
                or record.definition.class_source.casefold()
                == class_source.casefold()
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
    source_files = _load_class_files(directory)
    records = [
        ClassRecord(
            definition=definition,
            features=tuple(
                feature
                for source_file in source_files
                for feature in source_file.class_features
                if feature.class_name.casefold() == definition.name.casefold()
                and feature.class_source.casefold() == definition.source.casefold()
            ),
        )
        for source_file in source_files
        for definition in source_file.classes
    ]
    return SourceCatalog(
        records,
        name_of=lambda record: record.definition.public_name,
        source_of=lambda record: record.definition.source,
        source_priority=SOURCE_PRIORITY,
    )


def load_subclass_catalog(directory: str | Path) -> SubclassCatalog:
    source_files = _load_class_files(directory)
    records = [
        SubclassRecord(
            definition=definition,
            features=tuple(
                feature
                for source_file in source_files
                for feature in source_file.subclass_features
                if feature.class_name.casefold() == definition.class_name.casefold()
                and feature.class_source.casefold()
                == definition.class_source.casefold()
                and feature.subclass_short_name.casefold()
                == (definition.short_name or definition.name).casefold()
                and feature.subclass_source.casefold()
                == definition.source.casefold()
            ),
        )
        for source_file in source_files
        for definition in source_file.subclasses
    ]
    return SubclassCatalog(records)


def _load_class_files(directory: str | Path) -> list[ClassFileSchema]:
    class_dir = Path(directory) / "class"
    if not class_dir.is_dir():
        return []
    return [
        ClassFileSchema.model_validate(load_json(path))
        for path in sorted(class_dir.glob("class-*.json"))
    ]
