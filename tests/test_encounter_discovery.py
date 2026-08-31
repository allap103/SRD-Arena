from __future__ import annotations

import json
from pathlib import Path

from srd_arena.content.encounters import EncounterCatalog


def test_catalog_lists_only_valid_encounter_directories(tmp_path: Path) -> None:
    valid = tmp_path / "valid"
    valid.mkdir()
    (valid / "encounter.json").write_text("{}", encoding="utf-8")
    (valid / "config.json").write_text(
        json.dumps({"display_name": "Valid Encounter"}),
        encoding="utf-8",
    )
    missing_config = tmp_path / "missing_config"
    missing_config.mkdir()
    (missing_config / "encounter.json").write_text("{}", encoding="utf-8")
    missing_encounter = tmp_path / "missing_encounter"
    missing_encounter.mkdir()
    (missing_encounter / "config.json").write_text(
        json.dumps({"display_name": "Missing Encounter"}),
        encoding="utf-8",
    )
    invalid_config = tmp_path / "invalid_config"
    invalid_config.mkdir()
    (invalid_config / "encounter.json").write_text("{}", encoding="utf-8")
    (invalid_config / "config.json").write_text(
        json.dumps({"display_name": "Invalid", "grid_opacity": 2.0}),
        encoding="utf-8",
    )

    encounters = EncounterCatalog(encounter_root=tmp_path).available_encounters()

    assert [(encounter.id, encounter.label) for encounter in encounters] == [
        ("valid", "Valid Encounter")
    ]
