from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import SCENARIOS_ROOT

VALID_SCENARIO_SUBDIRS = ("creatures", "items", "encounters")


@dataclass(frozen=True)
class ScenarioInfo:
    id: str
    directory: Path
    label: str


def list_scenarios(root: Path = SCENARIOS_ROOT) -> list[ScenarioInfo]:
    scenarios: list[ScenarioInfo] = []
    if not root.exists():
        return scenarios
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        if all((directory / subdir).is_dir() for subdir in VALID_SCENARIO_SUBDIRS):
            scenarios.append(
                ScenarioInfo(
                    id=directory.name,
                    directory=directory.resolve(),
                    label=directory.name.replace("_", " ").replace("-", " ").title(),
                )
            )
    return scenarios
