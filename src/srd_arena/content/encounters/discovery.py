"""Discover directories containing valid authored encounter configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from srd_arena.content.common.paths import ENCOUNTERS_ROOT
from srd_arena.content.common.sources import load_json

from .schema import EncounterConfigSchema


@dataclass(frozen=True)
class EncounterSource:
    """Pair a stable encounter ID and directory with validated configuration."""

    id: str
    directory: Path
    folder: tuple[str, ...]
    schema: EncounterConfigSchema


def discover_encounters(root: Path = ENCOUNTERS_ROOT) -> tuple[EncounterSource, ...]:
    """Return valid encounter directories at any depth beneath the root.

    The root-relative POSIX path is the stable catalog ID. Its parent parts
    preserve authoring folders for presentation without coupling loading to a
    particular frontend.
    """

    if not root.exists():
        return ()
    discovered: list[EncounterSource] = []
    directories = sorted(
        {path.parent for path in root.rglob("encounter.json") if path.is_file()},
        key=lambda path: (
            tuple(part.casefold() for part in path.relative_to(root).parts),
            path.relative_to(root).parts,
        ),
    )
    for directory in directories:
        config_path = directory / "config.json"
        if not config_path.is_file():
            continue
        try:
            schema = EncounterConfigSchema.model_validate(load_json(config_path))
        except OSError, ValueError, ValidationError:
            continue
        relative = directory.relative_to(root)
        discovered.append(
            EncounterSource(
                id=relative.as_posix(),
                directory=directory.resolve(),
                folder=relative.parts[:-1],
                schema=schema,
            )
        )
    return tuple(discovered)
