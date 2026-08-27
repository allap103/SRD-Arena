"""Application use cases for discovering and starting games."""

from __future__ import annotations

from dataclasses import dataclass

from srd_arena.application.game import RunningGame
from srd_arena.application.scenarios import ScenarioRepository, ScenarioSummary


@dataclass(frozen=True)
class GameStartup:
    """Discover scenarios and create sessions through an injected source."""

    scenarios: ScenarioRepository

    def available_scenarios(self) -> tuple[ScenarioSummary, ...]:
        return self.scenarios.available_scenarios()

    def start_scenario(
        self,
        scenario_id: str,
        *,
        automatic_action_limit: int | None = None,
    ) -> RunningGame:
        scenario = self.scenarios.load_scenario(scenario_id)
        return RunningGame(
            scenario.create_session(
                automatic_action_limit=automatic_action_limit,
            )
        )
