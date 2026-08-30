"""Application contracts for discovering and loading game scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from srd_arena.domain.creatures import Creature
from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.domain.equipment import Item
from srd_arena.domain.geometry import GeometryConfig
from srd_arena.engine.session import Session

DEFAULT_GRID_COLOR = "#d3d3d3"


@dataclass(frozen=True)
class ScenarioPresentation:
    """Optional visual metadata supplied to graphical driving adapters."""

    background_image: str | None = None
    grid_color: str = DEFAULT_GRID_COLOR
    grid_opacity: float = 1.0


@dataclass(frozen=True)
class ScenarioSummary:
    """Scenario information suitable for selection by any driving adapter."""

    id: str
    label: str
    presentation: ScenarioPresentation = ScenarioPresentation()


@dataclass(frozen=True)
class LoadedScenario:
    """Domain definitions required to start one game session."""

    display_name: str
    encounters: dict[str, EncounterDefinition]
    creatures: tuple[Creature, ...]
    items: tuple[Item, ...]
    encounter_order: tuple[str, ...]
    start_scene: str
    geometry_config: GeometryConfig

    def get_creature(self, creature_id: str) -> Creature:
        """Return a loaded creature template by its authored identifier.

        >>> from srd_arena.domain.creatures import Attributes, Equipment, Inventory
        >>> hero = Creature("hero", "Hero", "", Inventory(),
        ...     Attributes(10, 1, 10, 10, 10, 10, 10, 10, 10), Equipment())
        >>> scenario = LoadedScenario("Demo", {}, (hero,), (), (), "intro", GeometryConfig())
        >>> scenario.get_creature("hero").name
        'Hero'
        """

        for creature in self.creatures:
            if creature.id == creature_id:
                return creature
        raise KeyError(f"Creature '{creature_id}' not found.")

    def create_session(
        self,
        *,
        pace_automatic_actions: bool = False,
    ) -> Session:
        """Create an isolated engine session from the loaded definitions.

        >>> scenario = LoadedScenario("Demo", {}, (), (), (), "intro", GeometryConfig())
        >>> first = scenario.create_session()
        >>> second = scenario.create_session()
        >>> isinstance(first, Session) and first is not second
        True
        """

        return Session(
            encounters=self.encounters,
            creature_templates={creature.id: creature for creature in self.creatures},
            item_templates={item.id: item for item in self.items},
            start_scene_id=self.start_scene,
            pace_automatic_actions=pace_automatic_actions,
            geometry_config=self.geometry_config,
        )


class ScenarioRepository(Protocol):
    """Source port for scenario discovery and loading."""

    def available_scenarios(self) -> tuple[ScenarioSummary, ...]: ...

    def load_scenario(
        self,
        scenario_id: str,
    ) -> LoadedScenario: ...
