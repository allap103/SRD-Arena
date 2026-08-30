from __future__ import annotations

from typing import cast

from srd_arena.scenarios.catalog import ScenarioCatalog
from srd_arena.scenarios.models import (
    LoadedScenario,
    ScenarioRepository,
    ScenarioSummary,
)


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


def test_scenario_catalog_lists_frontend_neutral_summaries() -> None:
    summary = ScenarioSummary(
        id="example",
        label="Example Encounter",
    )
    repository = ScenarioRepositoryStub(summaries=(summary,))

    scenarios = ScenarioCatalog(repository).available_scenarios()

    assert scenarios == (summary,)


def test_scenario_catalog_creates_session_from_repository_result() -> None:
    session = object()
    create_session_calls = 0

    class LoadedScenarioStub:
        @staticmethod
        def create_session() -> object:
            nonlocal create_session_calls
            create_session_calls += 1
            return session

    repository = ScenarioRepositoryStub(
        loaded=cast(LoadedScenario, LoadedScenarioStub())
    )

    created_session = ScenarioCatalog(
        cast(ScenarioRepository, repository)
    ).start_scenario("example")

    assert repository.loaded_ids == ["example"]
    assert create_session_calls == 1
    assert created_session is session
