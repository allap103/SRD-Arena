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
        """Return scenario summaries supplied by the configured repository.

        >>> from unittest.mock import Mock
        >>> repository = Mock()
        >>> repository.available_scenarios.return_value = (ScenarioSummary("demo", "Demo"),)
        >>> GameStartup(repository).available_scenarios()[0].id
        'demo'
        """
        return self.scenarios.available_scenarios()

    def start_scenario(
        self,
        scenario_id: str,
        *,
        pace_automatic_actions: bool = False,
    ) -> RunningGame:
        """Load a scenario and wrap its new engine session as a running game.

        >>> from unittest.mock import Mock
        >>> repository, scenario, engine = Mock(), Mock(), Mock()
        >>> repository.load_scenario.return_value = scenario
        >>> scenario.create_session.return_value = engine
        >>> game = GameStartup(repository).start_scenario("demo")
        >>> isinstance(game, RunningGame)
        True
        >>> repository.load_scenario.assert_called_once_with("demo")
        """
        scenario = self.scenarios.load_scenario(scenario_id)
        return RunningGame(
            scenario.create_session(
                pace_automatic_actions=pace_automatic_actions,
            )
        )
