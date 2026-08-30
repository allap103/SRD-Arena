"""Discover available scenarios and construct their engine sessions."""

from __future__ import annotations

from dataclasses import dataclass

from srd_arena.engine.session import Session

from .models import ScenarioRepository, ScenarioSummary


@dataclass(frozen=True)
class ScenarioCatalog:
    """Discover scenarios and create sessions through an injected source."""

    repository: ScenarioRepository

    def available_scenarios(self) -> tuple[ScenarioSummary, ...]:
        """Return scenario summaries supplied by the configured repository.

        >>> from unittest.mock import Mock
        >>> repository = Mock()
        >>> repository.available_scenarios.return_value = (ScenarioSummary("demo", "Demo"),)
        >>> ScenarioCatalog(repository).available_scenarios()[0].id
        'demo'
        """
        return self.repository.available_scenarios()

    def start_scenario(self, scenario_id: str) -> Session:
        """Load a scenario and create its isolated engine session.

        >>> from unittest.mock import Mock
        >>> repository, scenario, engine = Mock(), Mock(), Mock()
        >>> repository.load_scenario.return_value = scenario
        >>> scenario.create_session.return_value = engine
        >>> session = ScenarioCatalog(repository).start_scenario("demo")
        >>> session is engine
        True
        >>> repository.load_scenario.assert_called_once_with("demo")
        """
        scenario = self.repository.load_scenario(scenario_id)
        return scenario.create_session()
