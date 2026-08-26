"""Filesystem-backed scenario discovery and content assembly."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from srd_arena.application.scenarios import (
    DEFAULT_GRID_COLOR,
    LoadedScenario,
    ScenarioPresentation,
    ScenarioSummary,
)
from srd_arena.content.character_options.classes import (
    load_class_catalog,
    load_optional_feature_catalog,
    load_subclass_catalog,
)
from srd_arena.content.common.paths import (
    IMAGES_ROOT,
    SCENARIOS_ROOT,
    SYSTEM_CONTENT_ROOT,
)
from srd_arena.content.creatures import (
    load_bestiary_catalog,
    load_player_character_templates,
)
from srd_arena.content.encounters import list_scenarios, load_encounter
from srd_arena.content.equipment import load_system_items
from srd_arena.content.spells import load_spell_catalog
from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.domain.geometry import GeometryConfig


@dataclass(frozen=True)
class _ScenarioConfig:
    display_name: str = "Unnamed Scenario"
    encounters: tuple[str, ...] = ("goblin_encounter",)
    geometry_config: GeometryConfig = field(default_factory=GeometryConfig)
    presentation: ScenarioPresentation = field(default_factory=ScenarioPresentation)


@dataclass(frozen=True)
class FilesystemScenarioRepository:
    """Load authored scenarios and system content from the filesystem."""

    scenario_root: Path = SCENARIOS_ROOT
    system_directory: Path = SYSTEM_CONTENT_ROOT
    image_root: Path = IMAGES_ROOT

    def available_scenarios(self) -> tuple[ScenarioSummary, ...]:
        return tuple(
            ScenarioSummary(
                id=scenario.id,
                label=scenario.label,
                presentation=_load_config(
                    scenario.directory / "config.json"
                ).presentation,
            )
            for scenario in list_scenarios(self.scenario_root)
        )

    def load_scenario(
        self,
        scenario_id: str,
    ) -> LoadedScenario:
        scenario = next(
            (
                candidate
                for candidate in list_scenarios(self.scenario_root)
                if candidate.id == scenario_id
            ),
            None,
        )
        if scenario is None:
            raise KeyError(f"Unknown scenario '{scenario_id}'.")
        return self._load_directory(scenario.directory)

    def _load_directory(
        self,
        directory: Path,
        *,
        start_scene: str | None = None,
    ) -> LoadedScenario:
        config = _load_config(directory / "config.json")
        bestiary = load_bestiary_catalog(self.system_directory)
        classes = load_class_catalog(self.system_directory)
        subclasses = load_subclass_catalog(self.system_directory)
        spells = load_spell_catalog(self.system_directory)
        optional_features = load_optional_feature_catalog(self.system_directory)
        player_characters = load_player_character_templates(
            directory / "player_characters"
        )
        loaded_encounters = [
            load_encounter(
                path,
                bestiary,
                classes,
                player_characters,
                optional_features,
                subclasses,
                spells,
            )
            for path in (directory / "encounters").glob("*")
        ]
        encounters = {
            encounter.definition.id: encounter.definition
            for encounter in loaded_encounters
        }
        creatures_by_id = {
            creature.id: creature
            for encounter in loaded_encounters
            for creature in encounter.creatures
        }
        _link_encounters(encounters, config.encounters)
        return LoadedScenario(
            display_name=config.display_name,
            encounters=encounters,
            creatures=tuple(creatures_by_id.values()),
            items=tuple(load_system_items(self.system_directory)),
            encounter_order=config.encounters,
            start_scene=start_scene or config.encounters[0],
            geometry_config=config.geometry_config,
        )


def load_scenario(
    scenario_directory: str | Path,
    *,
    start_scene: str | None = None,
    system_directory: str | Path = SYSTEM_CONTENT_ROOT,
) -> LoadedScenario:
    """Load one filesystem scenario without constructing a frontend."""

    return FilesystemScenarioRepository(
        system_directory=Path(system_directory)
    )._load_directory(
        Path(scenario_directory),
        start_scene=start_scene,
    )


def _link_encounters(
    encounters: dict[str, EncounterDefinition],
    encounter_order: tuple[str, ...],
) -> None:
    if not encounter_order:
        raise ValueError("A scenario must contain at least one encounter.")
    missing = [
        encounter_id
        for encounter_id in encounter_order
        if encounter_id not in encounters
    ]
    if missing:
        raise ValueError(
            f"Scenario references missing encounters: {', '.join(missing)}"
        )
    for index, encounter_id in enumerate(encounter_order):
        next_encounter_id = (
            encounter_order[index + 1]
            if index + 1 < len(encounter_order)
            else encounter_id
        )
        encounter = encounters[encounter_id]
        if encounter.victory is None or encounter.defeat is None:
            raise ValueError(f"Encounter '{encounter_id}' must define transitions.")
        encounter.victory.next_encounter_id = next_encounter_id
        encounter.defeat.next_encounter_id = encounter_id


def _load_config(path: Path) -> _ScenarioConfig:
    if not path.exists():
        return _ScenarioConfig()
    with path.open("r", encoding="utf-8") as config_file:
        payload = json.load(config_file)
    encounters = payload.get("encounters")
    geometry = payload.get("geometry", {})
    configured_opacity = payload.get("grid_opacity", 1.0)
    grid_opacity = (
        min(max(float(configured_opacity), 0.0), 1.0)
        if isinstance(configured_opacity, (int, float))
        else 1.0
    )
    background_image = payload.get("background_image")
    grid_color = payload.get("grid_color")
    threshold = GeometryConfig().directional_area_cell_coverage_threshold
    if isinstance(geometry, dict):
        configured = geometry.get("directional_area_cell_coverage_threshold")
        if isinstance(configured, (int, float)):
            threshold = min(max(float(configured), 0.0), 1.0)
    return _ScenarioConfig(
        display_name=str(payload.get("display_name", "Unnamed Scenario")),
        encounters=(
            tuple(str(encounter_id) for encounter_id in encounters)
            if isinstance(encounters, list) and encounters
            else ("goblin_encounter",)
        ),
        geometry_config=GeometryConfig(
            directional_area_cell_coverage_threshold=threshold
        ),
        presentation=ScenarioPresentation(
            background_image=(
                background_image
                if isinstance(background_image, str) and background_image
                else None
            ),
            grid_color=(
                grid_color
                if isinstance(grid_color, str) and grid_color
                else DEFAULT_GRID_COLOR
            ),
            grid_opacity=grid_opacity,
        ),
    )
