"""Discover scenario directories that contain the required authored files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from srd_arena.content.common.paths import SCENARIOS_ROOT

VALID_SCENARIO_SUBDIRS = ("encounters",)


@dataclass(frozen=True)
class ScenarioInfo:
    """Describe a loadable scenario without parsing its encounter content."""

    id: str
    directory: Path
    label: str


def list_scenarios(root: Path = SCENARIOS_ROOT) -> list[ScenarioInfo]:
    """Return valid scenario directories for a launcher or other client."""

    scenarios: list[ScenarioInfo] = []
    if not root.exists():
        return scenarios
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        if all((directory / subdir).is_dir() for subdir in VALID_SCENARIO_SUBDIRS):
            config_path = directory / "config.json"
            if not config_path.is_file():
                continue
            with config_path.open(encoding="utf-8") as config_file:
                config = json.load(config_file)
            display_name = config.get("display_name")
            if not isinstance(display_name, str) or not display_name.strip():
                continue
            scenarios.append(
                ScenarioInfo(
                    id=directory.name,
                    directory=directory.resolve(),
                    label=display_name.strip(),
                )
            )
    return scenarios
