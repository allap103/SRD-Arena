from __future__ import annotations

import json
from pathlib import Path

from srd_arena.content.scenarios import ScenarioCatalog


def test_catalog_lists_only_valid_scenario_directories(tmp_path: Path) -> None:
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
    invalid_config = tmp_path / "invalid_config"
    (invalid_config / "encounters").mkdir(parents=True)
    (invalid_config / "config.json").write_text(
        json.dumps({"display_name": "Invalid", "grid_opacity": 2.0}),
        encoding="utf-8",
    )

    scenarios = ScenarioCatalog(scenario_root=tmp_path).available_scenarios()

    assert [(scenario.id, scenario.label) for scenario in scenarios] == [
        ("valid", "Valid Scenario")
    ]
