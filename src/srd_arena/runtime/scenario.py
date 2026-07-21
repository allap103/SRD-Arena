from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..content.loaders import (
    load_bestiary_stat_blocks,
    load_class_blocks,
    load_custom_stat_blocks,
    load_optional_feature_blocks,
    load_encounter,
    load_spell_catalog,
    load_subclass_blocks,
    load_system_items,
)
from ..domain.creatures import Creature
from ..domain.item import Item
from ..domain.config import (
    DEFAULT_DIRECTIONAL_AOE_CELL_COVERAGE_THRESHOLD,
    RulesConfig,
)
from ..domain.scene import Scene
from ..runtime.session import Session
from ..content.paths import SCENARIOS_ROOT, SYSTEM_CONTENT_ROOT

DEFAULT_SCENARIO_DIR = SCENARIOS_ROOT / "sample_game"
DEFAULT_SYSTEM_CONTENT_DIR = SYSTEM_CONTENT_ROOT


@dataclass(frozen=True)
class GameSettings:
    encounters: tuple[str, ...] = ("goblin_encounter",)
    rules_config: RulesConfig = field(default_factory=RulesConfig)


class Scenario:
    scenes: dict[str, Scene]
    creatures: list[Creature]
    items: list[Item]
    rules_config: RulesConfig

    def __init__(
        self,
        directory: str | Path = DEFAULT_SCENARIO_DIR,
        start_scene: str | None = None,
        system_directory: str | Path = DEFAULT_SYSTEM_CONTENT_DIR,
        control_mode: str = "default",
    ):
        self.directory = Path(directory)
        self.system_directory = Path(system_directory)
        settings = self._load_settings(self.directory / "settings.json")
        self.rules_config = settings.rules_config
        self.stat_blocks = load_bestiary_stat_blocks(self.system_directory)
        self.class_blocks = load_class_blocks(self.system_directory)
        self.subclass_blocks = load_subclass_blocks(self.system_directory)
        self.spell_catalog = load_spell_catalog(self.system_directory)
        self.optional_feature_blocks = load_optional_feature_blocks(self.system_directory)
        self.custom_stat_blocks = load_custom_stat_blocks(self.directory / "custom_stat_blocks")
        self.scenes, self.creatures = self.load_encounters_from_directory(
            self.directory / "encounters"
        )
        self.encounter_order = settings.encounters
        self._link_encounters()
        self.items = load_system_items(self.system_directory)
        self.start_scene = start_scene or self.encounter_order[0]
        self.control_mode = control_mode

    def load_encounters_from_directory(
        self, directory: str | Path
    ) -> tuple[dict[str, Scene], list[Creature]]:
        loaded = [
            load_encounter(
                path,
                self.stat_blocks,
                self.class_blocks,
                self.custom_stat_blocks,
                self.optional_feature_blocks,
                self.subclass_blocks,
                self.spell_catalog,
            )
            for path in Path(directory).glob("*")
        ]
        creatures_by_id = {
            creature.id: creature
            for encounter in loaded
            for creature in encounter.creatures
        }
        return (
            {encounter.scene.id: encounter.scene for encounter in loaded},
            list(creatures_by_id.values()),
        )

    def _link_encounters(self) -> None:
        if not self.encounter_order:
            raise ValueError("A scenario must contain at least one encounter.")
        missing = [encounter_id for encounter_id in self.encounter_order if encounter_id not in self.scenes]
        if missing:
            raise ValueError(f"Scenario references missing encounters: {', '.join(missing)}")
        for index, encounter_id in enumerate(self.encounter_order):
            next_encounter_id = (
                self.encounter_order[index + 1]
                if index + 1 < len(self.encounter_order)
                else encounter_id
            )
            encounter = self.scenes[encounter_id].encounter
            encounter.victory.next_scene = next_encounter_id
            encounter.defeat.next_scene = encounter_id
            if encounter.flee is not None:
                encounter.flee.next_scene = encounter_id

    def get_creature(self, actor_id: str) -> Creature:
        for creature in self.creatures:
            if creature.id == actor_id:
                return creature
        raise KeyError(f"Creature '{actor_id}' not found.")

    def create_session(
        self,
        player_creature_id: str = "player",
        control_mode: str | None = None,
    ) -> Session:
        return Session(
            scenes=self.scenes,
            player=self.get_creature(player_creature_id),
            creature_templates={creature.id: creature for creature in self.creatures},
            item_templates={item.id: item for item in self.items},
            start_scene_id=self.start_scene,
            scenario_dir=self.directory,
            control_mode=control_mode or self.control_mode,
            rules_config=self.rules_config,
        )

    def _load_settings(self, path: Path) -> GameSettings:
        if not path.exists():
            return GameSettings()
        with path.open("r", encoding="utf-8") as config_file:
            payload = json.load(config_file)
        encounters = payload.get("encounters")
        rules = payload.get("rules", {})
        threshold = DEFAULT_DIRECTIONAL_AOE_CELL_COVERAGE_THRESHOLD
        if isinstance(rules, dict):
            configured = rules.get("directional_aoe_cell_coverage_threshold")
            if isinstance(configured, (int, float)):
                threshold = min(max(float(configured), 0.0), 1.0)
        return GameSettings(
            encounters=(
                tuple(str(encounter_id) for encounter_id in encounters)
                if isinstance(encounters, list) and encounters
                else ("goblin_encounter",)
            ),
            rules_config=RulesConfig(directional_aoe_cell_coverage_threshold=threshold),
        )
