from __future__ import annotations

import json
from pathlib import Path

from srd_arena.application import startup
from srd_arena.application.startup import GameStartup


def test_game_startup_lists_frontend_neutral_scenario_summaries(tmp_path: Path) -> None:
    scenario_directory = tmp_path / "example"
    (scenario_directory / "encounters").mkdir(parents=True)
    (scenario_directory / "config.json").write_text(
        json.dumps({"display_name": "Example Encounter"}),
        encoding="utf-8",
    )

    scenarios = GameStartup(tmp_path).available_scenarios()

    assert len(scenarios) == 1
    assert scenarios[0].id == "example"
    assert scenarios[0].label == "Example Encounter"
    assert scenarios[0].directory == scenario_directory.resolve()


def test_game_startup_loads_scenario_before_creating_session(
    monkeypatch,
    tmp_path: Path,
) -> None:
    session = object()
    item = object()
    constructed_with: list[str | Path] = []

    class ScenarioStub:
        def __init__(self, directory: str | Path) -> None:
            constructed_with.append(directory)
            self.directory = Path(directory)
            self.items = [item]

        def create_session(self):
            return session

    monkeypatch.setattr(startup, "Scenario", ScenarioStub)

    running_game = GameStartup().start_scenario(tmp_path)

    assert constructed_with == [tmp_path]
    assert running_game.scenario_directory == tmp_path
    assert running_game.items == (item,)
    assert running_game.session is session
