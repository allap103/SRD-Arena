"""Application contracts for discovering and loading game scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from srd_arena.domain.creatures import Creature
from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.domain.equipment import Item
from srd_arena.domain.geometry import GeometryConfig
from srd_arena.runtime.session import Session


@dataclass(frozen=True)
class ScenarioSummary:
    """Scenario information suitable for selection by any driving adapter."""

    id: str
    label: str
    directory: Path


@dataclass(frozen=True)
class LoadedScenario:
    """Domain definitions required to start one game session."""

    directory: Path
    display_name: str
    encounters: dict[str, EncounterDefinition]
    creatures: tuple[Creature, ...]
    items: tuple[Item, ...]
    encounter_order: tuple[str, ...]
    start_scene: str
    geometry_config: GeometryConfig

    def get_creature(self, creature_id: str) -> Creature:
        """Return a loaded creature template by its authored identifier."""

        for creature in self.creatures:
            if creature.id == creature_id:
                return creature
        raise KeyError(f"Creature '{creature_id}' not found.")

    def create_session(self) -> Session:
        """Create an isolated runtime session from the loaded definitions."""

        return Session(
            encounters=self.encounters,
            creature_templates={creature.id: creature for creature in self.creatures},
            item_templates={item.id: item for item in self.items},
            start_scene_id=self.start_scene,
            geometry_config=self.geometry_config,
        )


class ScenarioRepository(Protocol):
    """Source port for scenario discovery and loading."""

    def available_scenarios(self) -> tuple[ScenarioSummary, ...]: ...

    def load_scenario(
        self,
        scenario_directory: str | Path,
        *,
        start_scene: str | None = None,
    ) -> LoadedScenario: ...
