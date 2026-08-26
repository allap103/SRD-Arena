from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from srd_arena.content.common.paths import SCENARIOS_ROOT
from srd_arena.content.encounters import list_scenarios
from srd_arena.domain.equipment.items import Item
from srd_arena.runtime.scenario import Scenario
from srd_arena.runtime.session import Session


@dataclass(frozen=True)
class AvailableScenario:
    """Scenario information needed by a frontend selection screen."""

    id: str
    label: str
    directory: Path


@dataclass(frozen=True)
class RunningGame:
    """A loaded scenario and its newly created runtime session."""

    scenario_directory: Path
    items: tuple[Item, ...]
    session: Session


@dataclass(frozen=True)
class GameStartup:
    """Discover scenarios and create frontend-independent game sessions."""

    scenario_root: Path = SCENARIOS_ROOT

    def available_scenarios(self) -> tuple[AvailableScenario, ...]:
        return tuple(
            AvailableScenario(
                id=scenario.id,
                label=scenario.label,
                directory=scenario.directory,
            )
            for scenario in list_scenarios(self.scenario_root)
        )

    def start_scenario(self, scenario_directory: str | Path) -> RunningGame:
        scenario = Scenario(scenario_directory)
        return RunningGame(
            scenario_directory=scenario.directory,
            items=tuple(scenario.items),
            session=scenario.create_session(),
        )
