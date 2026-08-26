"""Application use cases for discovering and starting games."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from srd_arena.application.scenarios import ScenarioRepository, ScenarioSummary
from srd_arena.domain.equipment.items import Item
from srd_arena.runtime.session import Session


@dataclass(frozen=True)
class RunningGame:
    """A loaded scenario and its newly created runtime session."""

    scenario_directory: Path
    items: tuple[Item, ...]
    session: Session


@dataclass(frozen=True)
class GameStartup:
    """Discover scenarios and create sessions through an injected source."""

    scenarios: ScenarioRepository

    def available_scenarios(self) -> tuple[ScenarioSummary, ...]:
        return self.scenarios.available_scenarios()

    def start_scenario(self, scenario_directory: str | Path) -> RunningGame:
        scenario = self.scenarios.load_scenario(scenario_directory)
        return RunningGame(
            scenario_directory=scenario.directory,
            items=scenario.items,
            session=scenario.create_session(),
        )
