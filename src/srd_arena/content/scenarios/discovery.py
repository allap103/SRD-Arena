"""Discover directories containing valid authored scenario configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from srd_arena.content.common.paths import SCENARIOS_ROOT
from srd_arena.content.common.sources import load_json

from .schema import ScenarioSchema


@dataclass(frozen=True)
class ScenarioSource:
    """Pair a stable scenario ID and directory with validated configuration."""

    id: str
    directory: Path
    schema: ScenarioSchema


def discover_scenarios(root: Path = SCENARIOS_ROOT) -> tuple[ScenarioSource, ...]:
    """Return directories with valid configuration and encounter content.

    Malformed entries are omitted so one bad user-authored directory cannot
    prevent the scenario picker from opening.

    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as directory:
    ...     root = Path(directory)
    ...     scenario = root / "demo"
    ...     (scenario / "encounters").mkdir(parents=True)
    ...     _ = (scenario / "config.json").write_text(
    ...         '{"display_name": "Demo Battle"}', encoding="utf-8")
    ...     [(entry.id, entry.schema.display_name) for entry in discover_scenarios(root)]
    [('demo', 'Demo Battle')]
    """

    if not root.exists():
        return ()
    discovered: list[ScenarioSource] = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        config_path = directory / "config.json"
        if not (directory / "encounters").is_dir() or not config_path.is_file():
            continue
        try:
            schema = ScenarioSchema.model_validate(load_json(config_path))
        except OSError, ValueError, ValidationError:
            continue
        discovered.append(
            ScenarioSource(
                id=directory.name,
                directory=directory.resolve(),
                schema=schema,
            )
        )
    return tuple(discovered)
