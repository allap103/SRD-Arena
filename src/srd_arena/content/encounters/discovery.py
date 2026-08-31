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
    schema: EncounterConfigSchema


def discover_encounters(root: Path = ENCOUNTERS_ROOT) -> tuple[EncounterSource, ...]:
    """Return directories containing valid config and encounter documents."""

    if not root.exists():
        return ()
    discovered: list[EncounterSource] = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        config_path = directory / "config.json"
        if not (directory / "encounter.json").is_file() or not config_path.is_file():
            continue
        try:
            schema = EncounterConfigSchema.model_validate(load_json(config_path))
        except OSError, ValueError, ValidationError:
            continue
        discovered.append(
            EncounterSource(
                id=directory.name,
                directory=directory.resolve(),
                schema=schema,
            )
        )
    return tuple(discovered)
