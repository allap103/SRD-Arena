from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .paths import SCENARIOS_ROOT

VALID_SCENARIO_SUBDIRS = ("encounters",)


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


def resolve_scenario_directory(
    scenario: str | None,
    *,
    current_directory: Path | None = None,
    scenarios_root: Path = SCENARIOS_ROOT,
) -> Path:
    """Resolve and validate an explicit scenario name or directory."""
    if scenario is None:
        raise FileNotFoundError("No scenario directory provided.")

    requested = Path(scenario).expanduser()
    if requested.is_absolute():
        candidates = [requested]
    else:
        candidates = [
            ((current_directory or Path.cwd()) / requested).resolve(),
            (scenarios_root / requested).resolve(),
        ]

    for candidate in candidates:
        if candidate.exists():
            return validate_scenario_directory(candidate)

    raise FileNotFoundError(
        "Could not find a scenario directory for "
        f"'{scenario}'. Tried the current working directory and content/scenarios/."
    )


def validate_scenario_directory(path: Path) -> Path:
    """Ensure a path has the minimum directory structure of a scenario."""
    if not path.is_dir():
        raise NotADirectoryError(f"'{path}' is not a directory.")

    missing = [
        subdir for subdir in VALID_SCENARIO_SUBDIRS if not (path / subdir).is_dir()
    ]
    if missing:
        raise FileNotFoundError(
            f"'{path}' is not a valid scenario directory. Missing: {', '.join(missing)}."
        )
    return path
