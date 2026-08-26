from __future__ import annotations

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
        self.loaded_ids: list[str] = []

    def available_scenarios(self) -> tuple[ScenarioSummary, ...]:
        return self.summaries

    def load_scenario(
        self,
        scenario_id: str,
    ) -> LoadedScenario:
        self.loaded_ids.append(scenario_id)
        if self.loaded is None:
            raise AssertionError("No loaded scenario was configured.")
        return self.loaded


def test_game_startup_lists_frontend_neutral_scenario_summaries() -> None:
    summary = ScenarioSummary(
        id="example",
        label="Example Encounter",
    )
    repository = ScenarioRepositoryStub(summaries=(summary,))

    scenarios = GameStartup(repository).available_scenarios()

    assert scenarios == (summary,)


def test_game_startup_creates_session_from_repository_result(
) -> None:
    session = object()
    received_limits: list[int | None] = []

    class LoadedScenarioStub:
        @staticmethod
        def create_session(
            *,
            automatic_action_limit: int | None = None,
        ):
            received_limits.append(automatic_action_limit)
            return session

    repository = ScenarioRepositoryStub(
        loaded=cast(LoadedScenario, LoadedScenarioStub())
    )

    running_game = GameStartup(cast(ScenarioRepository, repository)).start_scenario(
        "example",
        automatic_action_limit=1,
    )

    assert repository.loaded_ids == ["example"]
    assert received_limits == [1]
    assert not hasattr(running_game, "session")
    assert not hasattr(running_game, "_session")
