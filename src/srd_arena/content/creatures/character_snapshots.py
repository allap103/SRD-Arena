"""Load validated, level-specific snapshots for fixed character builds."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from srd_arena.content.common.sources import load_json
from srd_arena.domain.creatures import CharacterOptionRef, CharacterProfile

from .schema import (
    CharacterOptionReferenceSchema,
    CharacterProfileSchema,
    CreatureSchema,
    StatBlockReferenceSchema,
)


class CharacterLevelSnapshotSchema(BaseModel):
    """Validate one fully selected level of a fixed character build."""

    model_config = ConfigDict(extra="forbid")

    level: int = Field(ge=1, le=20)
    creature: CreatureSchema
    subclass_ref: CharacterOptionReferenceSchema | None = None
    feats: tuple[CharacterOptionReferenceSchema, ...] = ()
    weapon_masteries: tuple[str, ...] = ()
    deferred_options: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_matching_creature_level(self) -> CharacterLevelSnapshotSchema:
        """Require the snapshot label and compiled creature level to agree."""

        if self.creature.attributes.level != self.level:
            raise ValueError(
                "Snapshot level must match the nested creature attribute level."
            )
        return self


class CharacterBuildSchema(BaseModel):
    """Validate the identity and contiguous snapshots of one fixed build."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    species: CharacterOptionReferenceSchema
    background: CharacterOptionReferenceSchema
    class_ref: StatBlockReferenceSchema
    snapshots: tuple[CharacterLevelSnapshotSchema, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_contiguous_matching_snapshots(self) -> CharacterBuildSchema:
        """Require one ordered snapshot for every level starting at level 1."""

        levels = tuple(snapshot.level for snapshot in self.snapshots)
        expected = tuple(range(1, max(levels) + 1))
        if levels != expected:
            raise ValueError(
                "Character snapshots must be ordered, unique, and contiguous "
                "from level 1."
            )
        expected_class = (self.class_ref.name.casefold(), self.class_ref.source)
        for snapshot in self.snapshots:
            creature_class = snapshot.creature.class_ref
            if creature_class is None:
                continue
            actual_class = (creature_class.name.casefold(), creature_class.source)
            if actual_class != expected_class:
                raise ValueError(
                    "A snapshot creature class must match its containing build."
                )
        return self


@dataclass(frozen=True)
class CharacterSnapshotCatalog:
    """Index fixed character builds and compile independent creature templates."""

    builds: tuple[CharacterBuildSchema, ...]

    def available_build_ids(self) -> tuple[str, ...]:
        """Return stable build identifiers in deterministic order."""

        return tuple(sorted(build.id for build in self.builds))

    def find_build(self, build_id: str) -> CharacterBuildSchema:
        """Return a fixed build by its case-insensitive stable identifier."""

        normalized = build_id.casefold()
        build = next(
            (
                candidate
                for candidate in self.builds
                if candidate.id.casefold() == normalized
            ),
            None,
        )
        if build is None:
            raise KeyError(f"Unknown character build '{build_id}'.")
        return build

    def snapshot(
        self,
        build_id: str,
        level: int,
    ) -> CharacterLevelSnapshotSchema:
        """Return the authored snapshot for one build level."""

        build = self.find_build(build_id)
        snapshot = next(
            (candidate for candidate in build.snapshots if candidate.level == level),
            None,
        )
        if snapshot is None:
            raise KeyError(
                f"Character build '{build.id}' has no level {level} snapshot."
            )
        return snapshot

    def creature_template(
        self,
        build_id: str,
        level: int,
    ) -> CreatureSchema:
        """Compile a fresh creature schema from one canonical snapshot.

        The returned schema is independent of the catalog, allowing encounter
        construction to override its instance ID without mutating authored
        content.
        """

        build = self.find_build(build_id)
        snapshot = self.snapshot(build_id, level)
        data = snapshot.creature.model_dump(exclude_unset=True)
        data["class_ref"] = build.class_ref.model_dump()
        data["character_profile"] = {
            "build_id": build.id,
            "species": build.species.model_dump(),
            "background": build.background.model_dump(),
            "subclass": (
                snapshot.subclass_ref.model_dump()
                if snapshot.subclass_ref is not None
                else None
            ),
            "feats": [feat.model_dump() for feat in snapshot.feats],
            "selected_features": [
                feature.model_dump() for feature in snapshot.creature.optional_features
            ],
            "weapon_masteries": list(snapshot.weapon_masteries),
        }
        return CreatureSchema.model_validate(data)


def build_character_profile(
    schema: CharacterProfileSchema | None,
) -> CharacterProfile | None:
    """Translate selected content identities into a domain character profile."""

    if schema is None:
        return None
    return CharacterProfile(
        build_id=schema.build_id,
        species=CharacterOptionRef(
            name=schema.species.name,
            source=schema.species.source,
        ),
        background=CharacterOptionRef(
            name=schema.background.name,
            source=schema.background.source,
        ),
        subclass=(
            CharacterOptionRef(
                name=schema.subclass.name,
                source=schema.subclass.source,
            )
            if schema.subclass is not None
            else None
        ),
        feats=tuple(
            CharacterOptionRef(name=feat.name, source=feat.source)
            for feat in schema.feats
        ),
        selected_features=tuple(
            CharacterOptionRef(name=feature.name, source=feature.source)
            for feature in schema.selected_features
        ),
        weapon_masteries=schema.weapon_masteries,
    )


def load_character_snapshot_catalog(
    directory: str | Path,
) -> CharacterSnapshotCatalog:
    """Load fixed character-build files from a system content directory.

    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     root = Path(directory)
    ...     (root / "characters").mkdir()
    ...     _ = (root / "characters" / "hero.json").write_text(
    ...         '{"id":"hero","name":"Hero",'
    ...         '"species":{"name":"Human"},'
    ...         '"background":{"name":"Guard"},'
    ...         '"class_ref":{"name":"Fighter"},'
    ...         '"snapshots":[{"level":1,"creature":{'
    ...         '"id":"hero","attributes":{"level":1}}}]}',
    ...         encoding="utf-8",
    ...     )
    ...     catalog = load_character_snapshot_catalog(root)
    >>> catalog.available_build_ids()
    ('hero',)
    """

    characters_dir = Path(directory) / "characters"
    builds = tuple(
        CharacterBuildSchema.model_validate(load_json(path))
        for path in sorted(characters_dir.glob("*.json"))
    )
    ids = [build.id.casefold() for build in builds]
    duplicates = sorted(build_id for build_id in set(ids) if ids.count(build_id) > 1)
    if duplicates:
        raise ValueError("Character build IDs must be unique: " + ", ".join(duplicates))
    return CharacterSnapshotCatalog(builds)
