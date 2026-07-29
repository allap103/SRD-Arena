from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from srd_arena.content.loaders import (
    load_bestiary_catalog,
    load_class_catalog,
    load_player_character_templates,
    load_optional_feature_catalog,
    load_encounter,
    load_spell_catalog,
    load_subclass_catalog,
    load_system_items,
)
from srd_arena.content.paths import SCENARIOS_ROOT, SYSTEM_CONTENT_ROOT
from srd_arena.domain.creatures import Creature
from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.domain.equipment import Item
from srd_arena.domain.geometry import GeometryConfig

from .session import Session

DEFAULT_SCENARIO_DIR = SCENARIOS_ROOT / "sample_game"
DEFAULT_SYSTEM_CONTENT_DIR = SYSTEM_CONTENT_ROOT
DEFAULT_GRID_COLOR = "#d3d3d3"


@dataclass(frozen=True)
class ScenarioConfig:
    display_name: str = "Unnamed Scenario"
    encounters: tuple[str, ...] = ("goblin_encounter",)
    geometry_config: GeometryConfig = field(default_factory=GeometryConfig)
    background_image: str | None = None
    grid_color: str = DEFAULT_GRID_COLOR
    grid_opacity: float = 1.0


class Scenario:
    encounters: dict[str, EncounterDefinition]
    creatures: list[Creature]
    items: list[Item]
    geometry_config: GeometryConfig

    def __init__(
        self,
        directory: str | Path = DEFAULT_SCENARIO_DIR,
        start_scene: str | None = None,
        system_directory: str | Path = DEFAULT_SYSTEM_CONTENT_DIR,
    ):
        self.directory = Path(directory)
        self.system_directory = Path(system_directory)
        config = self._load_config(self.directory / "config.json")
        self.display_name = config.display_name
        self.geometry_config = config.geometry_config
        self.background_image = config.background_image
        self.grid_color = config.grid_color
        self.grid_opacity = config.grid_opacity
        self.bestiary = load_bestiary_catalog(self.system_directory)
        self.classes = load_class_catalog(self.system_directory)
        self.subclasses = load_subclass_catalog(self.system_directory)
        self.spells = load_spell_catalog(self.system_directory)
        self.optional_features = load_optional_feature_catalog(self.system_directory)
        self.player_characters = load_player_character_templates(
            self.directory / "player_characters"
        )
        self.encounters, self.creatures = self.load_encounters_from_directory(
            self.directory / "encounters"
        )
        self.encounter_order = config.encounters
        self._link_encounters()
        self.items = load_system_items(self.system_directory)
        self.start_scene = start_scene or self.encounter_order[0]

    def load_encounters_from_directory(
        self, directory: str | Path
    ) -> tuple[dict[str, EncounterDefinition], list[Creature]]:
        loaded = [
            load_encounter(
                path,
                self.bestiary,
                self.classes,
                self.player_characters,
                self.optional_features,
                self.subclasses,
                self.spells,
            )
            for path in Path(directory).glob("*")
        ]
        creatures_by_id = {
            creature.id: creature
            for encounter in loaded
            for creature in encounter.creatures
        }
        return (
            {encounter.definition.id: encounter.definition for encounter in loaded},
            list(creatures_by_id.values()),
        )

    def _link_encounters(self) -> None:
        if not self.encounter_order:
            raise ValueError("A scenario must contain at least one encounter.")
        missing = [
            encounter_id
            for encounter_id in self.encounter_order
            if encounter_id not in self.encounters
        ]
        if missing:
            raise ValueError(f"Scenario references missing encounters: {', '.join(missing)}")
        for index, encounter_id in enumerate(self.encounter_order):
            next_encounter_id = (
                self.encounter_order[index + 1]
                if index + 1 < len(self.encounter_order)
                else encounter_id
            )
            encounter = self.encounters[encounter_id]
            if encounter.victory is None or encounter.defeat is None:
                raise ValueError(
                    f"Encounter '{encounter_id}' must define transitions."
                )
            encounter.victory.next_encounter_id = next_encounter_id
            encounter.defeat.next_encounter_id = encounter_id

    def get_creature(self, creature_id: str) -> Creature:
        for creature in self.creatures:
            if creature.id == creature_id:
                return creature
        raise KeyError(f"Creature '{creature_id}' not found.")

    def create_session(self) -> Session:
        encounter = self.encounters[self.start_scene]
        team_by_creature = {
            creature_id: team
            for team in encounter.teams
            for creature_id in team.members
        }
        externally_controlled = [
            participant.creature_id
            for participant in encounter.participants
            if (
                participant.controller
                or team_by_creature[participant.creature_id].controller
            )
            == "external"
        ]
        if not externally_controlled:
            raise ValueError(
                f"Starting encounter '{encounter.id}' must configure at least one "
                "externally controlled creature."
            )
        return Session(
            encounters=self.encounters,
            primary_creature_id=externally_controlled[0],
            creature_templates={creature.id: creature for creature in self.creatures},
            item_templates={item.id: item for item in self.items},
            start_scene_id=self.start_scene,
            geometry_config=self.geometry_config,
            background_image=self.background_image,
            grid_color=self.grid_color,
            grid_opacity=self.grid_opacity,
        )

    def _load_config(self, path: Path) -> ScenarioConfig:
        if not path.exists():
            return ScenarioConfig()
        with path.open("r", encoding="utf-8") as config_file:
            payload = json.load(config_file)
        encounters = payload.get("encounters")
        geometry = payload.get("geometry", {})
        configured_grid_opacity = payload.get("grid_opacity", 1.0)
        grid_opacity = (
            min(max(float(configured_grid_opacity), 0.0), 1.0)
            if isinstance(configured_grid_opacity, (int, float))
            else 1.0
        )
        threshold = GeometryConfig().directional_area_cell_coverage_threshold
        if isinstance(geometry, dict):
            configured = geometry.get("directional_area_cell_coverage_threshold")
            if isinstance(configured, (int, float)):
                threshold = min(max(float(configured), 0.0), 1.0)
        return ScenarioConfig(
            display_name=str(payload.get("display_name", "Unnamed Scenario")),
            encounters=(
                tuple(str(encounter_id) for encounter_id in encounters)
                if isinstance(encounters, list) and encounters
                else ("goblin_encounter",)
            ),
            geometry_config=GeometryConfig(
                directional_area_cell_coverage_threshold=threshold
            ),
            background_image=(
                str(payload["background_image"])
                if isinstance(payload.get("background_image"), str)
                and payload["background_image"]
                else None
            ),
            grid_color=(
                str(payload["grid_color"])
                if isinstance(payload.get("grid_color"), str)
                and payload["grid_color"]
                else DEFAULT_GRID_COLOR
            ),
            grid_opacity=grid_opacity,
        )
