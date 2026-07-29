from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..content.loaders import (
    load_bestiary_stat_blocks,
    load_class_blocks,
    load_player_characters,
    load_optional_feature_blocks,
    load_encounter,
    load_spell_catalog,
    load_subclass_blocks,
    load_system_items,
)
from ..content.loaders.types import (
    ClassCatalog,
    OptionalFeatureCatalog,
    PlayerCharacterCatalog,
    SpellCatalog,
    StatBlockCatalog,
    SubclassCatalog,
)
from ..domain.creatures import Creature
from ..domain.encounters import EncounterDefinition
from ..domain.equipment import Item
from ..domain.geometry import GeometryConfig
from ..runtime.session import Session
from ..content.paths import SCENARIOS_ROOT, SYSTEM_CONTENT_ROOT

DEFAULT_SCENARIO_DIR = SCENARIOS_ROOT / "sample_game"
DEFAULT_SYSTEM_CONTENT_DIR = SYSTEM_CONTENT_ROOT


@dataclass(frozen=True)
class ScenarioConfig:
    display_name: str = "Unnamed Scenario"
    encounters: tuple[str, ...] = ("goblin_encounter",)
    geometry_config: GeometryConfig = field(default_factory=GeometryConfig)


@dataclass
class LoadedScenario:
    """A fully loaded scenario with no filesystem-loading responsibilities."""

    directory: Path
    system_directory: Path
    display_name: str
    geometry_config: GeometryConfig
    stat_blocks: StatBlockCatalog
    class_blocks: ClassCatalog
    subclass_blocks: SubclassCatalog
    spell_catalog: SpellCatalog
    optional_feature_blocks: OptionalFeatureCatalog
    player_characters: PlayerCharacterCatalog
    encounters: dict[str, EncounterDefinition]
    creatures: list[Creature]
    encounter_order: tuple[str, ...]
    items: list[Item]
    start_scene: str

    def get_creature(self, actor_id: str) -> Creature:
        for creature in self.creatures:
            if creature.id == actor_id:
                return creature
        raise KeyError(f"Creature '{actor_id}' not found.")

    def create_session(self) -> Session:
        encounter = self.encounters[self.start_scene]
        external_actor_ids = [
            actor_id
            for team in encounter.teams
            if team.controller == "external"
            for actor_id in team.members
        ]
        if not external_actor_ids:
            raise ValueError(
                f"Starting encounter '{encounter.id}' must configure at least one "
                "externally controlled creature."
            )
        return Session(
            encounters=self.encounters,
            player=self.get_creature(external_actor_ids[0]),
            creature_templates={creature.id: creature for creature in self.creatures},
            item_templates={item.id: item for item in self.items},
            start_scene_id=self.start_scene,
            geometry_config=self.geometry_config,
        )


class ScenarioLoader:
    """Load and validate scenario content from disk."""

    def __init__(
        self,
        system_directory: str | Path = DEFAULT_SYSTEM_CONTENT_DIR,
    ) -> None:
        self.system_directory = Path(system_directory)

    def load(
        self,
        directory: str | Path = DEFAULT_SCENARIO_DIR,
        *,
        start_scene: str | None = None,
    ) -> LoadedScenario:
        scenario_directory = Path(directory)
        config = self._load_config(scenario_directory / "config.json")
        stat_blocks = load_bestiary_stat_blocks(self.system_directory)
        class_blocks = load_class_blocks(self.system_directory)
        subclass_blocks = load_subclass_blocks(self.system_directory)
        spell_catalog = load_spell_catalog(self.system_directory)
        optional_feature_blocks = load_optional_feature_blocks(self.system_directory)
        player_characters = load_player_characters(
            scenario_directory / "player_characters"
        )
        encounters, creatures = self._load_encounters_from_directory(
            scenario_directory / "encounters",
            stat_blocks=stat_blocks,
            class_blocks=class_blocks,
            player_characters=player_characters,
            optional_feature_blocks=optional_feature_blocks,
            subclass_blocks=subclass_blocks,
            spell_catalog=spell_catalog,
        )
        self._link_encounters(encounters, config.encounters)
        return LoadedScenario(
            directory=scenario_directory,
            system_directory=self.system_directory,
            display_name=config.display_name,
            geometry_config=config.geometry_config,
            stat_blocks=stat_blocks,
            class_blocks=class_blocks,
            subclass_blocks=subclass_blocks,
            spell_catalog=spell_catalog,
            optional_feature_blocks=optional_feature_blocks,
            player_characters=player_characters,
            encounters=encounters,
            creatures=creatures,
            encounter_order=config.encounters,
            items=load_system_items(self.system_directory),
            start_scene=start_scene or config.encounters[0],
        )

    def _load_encounters_from_directory(
        self,
        directory: str | Path,
        *,
        stat_blocks: StatBlockCatalog,
        class_blocks: ClassCatalog,
        player_characters: PlayerCharacterCatalog,
        optional_feature_blocks: OptionalFeatureCatalog,
        subclass_blocks: SubclassCatalog,
        spell_catalog: SpellCatalog,
    ) -> tuple[dict[str, EncounterDefinition], list[Creature]]:
        loaded = [
            load_encounter(
                path,
                stat_blocks,
                class_blocks,
                player_characters,
                optional_feature_blocks,
                subclass_blocks,
                spell_catalog,
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

    def _link_encounters(
        self,
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
            assert encounter.victory is not None
            assert encounter.defeat is not None
            encounter.victory.next_encounter_id = next_encounter_id
            encounter.defeat.next_encounter_id = encounter_id

    def _load_config(self, path: Path) -> ScenarioConfig:
        if not path.exists():
            return ScenarioConfig()
        with path.open("r", encoding="utf-8") as config_file:
            payload = json.load(config_file)
        encounters = payload.get("encounters")
        geometry = payload.get("geometry", {})
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
        )
