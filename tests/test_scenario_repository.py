from __future__ import annotations

import json
from pathlib import Path

from srd_arena.infrastructure.scenarios import FilesystemScenarioRepository


def test_filesystem_repository_lists_valid_scenarios(tmp_path: Path) -> None:
    valid = tmp_path / "valid"
    (valid / "encounters").mkdir(parents=True)
    (valid / "config.json").write_text(
        json.dumps({"display_name": "Valid Scenario"}),
        encoding="utf-8",
    )
    missing_config = tmp_path / "missing_config"
    (missing_config / "encounters").mkdir(parents=True)
    missing_encounters = tmp_path / "missing_encounters"
    missing_encounters.mkdir()
    (missing_encounters / "config.json").write_text(
        json.dumps({"display_name": "Missing Encounters"}),
        encoding="utf-8",
    )

    scenarios = FilesystemScenarioRepository(
        scenario_root=tmp_path
    ).available_scenarios()

    assert [(scenario.id, scenario.label) for scenario in scenarios] == [
        ("valid", "Valid Scenario")
    ]
