from __future__ import annotations

from pathlib import Path
from typing import cast

from srd_arena.application.scenarios import (
    LoadedScenario,
    ScenarioRepository,
    ScenarioSummary,
)
from srd_arena.application.startup import GameStartup


class ScenarioRepositoryStub:
    def __init__(
        self,
        *,
        summaries: tuple[ScenarioSummary, ...] = (),
        loaded: LoadedScenario | None = None,
    ) -> None:
        self.summaries = summaries
        self.loaded = loaded
        self.loaded_directories: list[Path] = []

    def available_scenarios(self) -> tuple[ScenarioSummary, ...]:
        return self.summaries

    def load_scenario(
        self,
        scenario_directory: str | Path,
        *,
        start_scene: str | None = None,
    ) -> LoadedScenario:
        del start_scene
        self.loaded_directories.append(Path(scenario_directory))
        if self.loaded is None:
            raise AssertionError("No loaded scenario was configured.")
        return self.loaded


def test_game_startup_lists_frontend_neutral_scenario_summaries(
    tmp_path: Path,
) -> None:
    summary = ScenarioSummary(
        id="example",
        label="Example Encounter",
        directory=tmp_path / "example",
    )
    repository = ScenarioRepositoryStub(summaries=(summary,))

    scenarios = GameStartup(repository).available_scenarios()

    assert scenarios == (summary,)


def test_game_startup_creates_session_from_repository_result(
    tmp_path: Path,
) -> None:
    session = object()
    item = object()

    class LoadedScenarioStub:
        directory = tmp_path
        items = (item,)

        @staticmethod
        def create_session():
            return session

    repository = ScenarioRepositoryStub(
        loaded=cast(LoadedScenario, LoadedScenarioStub())
    )

    running_game = GameStartup(cast(ScenarioRepository, repository)).start_scenario(
        tmp_path
    )

    assert repository.loaded_directories == [tmp_path]
    assert running_game.scenario_directory == tmp_path
    assert running_game.items == (item,)
    assert running_game.session is session
