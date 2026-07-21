from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..content.loaders import (
    load_creature,
    load_bestiary_stat_blocks,
    load_class_blocks,
    load_custom_stat_blocks,
    load_item,
    load_optional_feature_blocks,
    load_scene,
    load_spell_catalog,
    load_subclass_blocks,
    load_system_item_catalog,
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
    start_scene: str = "welcome"
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
        self.system_item_catalog = load_system_item_catalog(self.system_directory)
        self.scenes = self.load_scenes_from_directory(self.directory / "scenes")
        self.creatures = self.load_creatures_from_directory(self.directory)
        self.items = self._merge_items(
            load_system_items(self.system_directory),
            self.load_items_from_directory(self.directory / "items"),
        )
        self.start_scene = start_scene or settings.start_scene
        self.control_mode = control_mode

    def load_creatures_from_directory(self, directory: str | Path) -> list[Creature]:
        creature_dir = Path(directory) / "actors"
        return [
            load_creature(
                path,
                self.stat_blocks,
                self.class_blocks,
                self.custom_stat_blocks,
                self.optional_feature_blocks,
                self.subclass_blocks,
                self.spell_catalog,
            )
            for path in creature_dir.glob("*")
        ]

    def load_items_from_directory(self, directory: str | Path) -> list[Item]:
        return [load_item(path, self.system_item_catalog) for path in Path(directory).glob("*")]

    def _merge_items(self, system_items: list[Item], local_items: list[Item]) -> list[Item]:
        items_by_id = {item.id: item for item in system_items}
        items_by_id.update({item.id: item for item in local_items})
        return list(items_by_id.values())

    def load_scenes_from_directory(self, directory: str | Path) -> dict[str, Scene]:
        return {
            scene.id: scene
            for scene in (load_scene(path) for path in Path(directory).glob("*"))
        }

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
        start_scene_id = self._resolve_start_scene_id(self.start_scene)
        return Session(
            scenes=self.scenes,
            player=self.get_creature(player_creature_id),
            creature_templates={creature.id: creature for creature in self.creatures},
            item_templates={item.id: item for item in self.items},
            start_scene_id=start_scene_id,
            scenario_dir=self.directory,
            control_mode=control_mode or self.control_mode,
            rules_config=self.rules_config,
        )

    def _resolve_start_scene_id(self, scene_id: str) -> str:
        visited: set[str] = set()
        current_scene_id = scene_id
        while current_scene_id not in visited:
            visited.add(current_scene_id)
            scene = self.scenes[current_scene_id]
            if scene.encounter is not None or not scene.choices:
                return current_scene_id
            if len(scene.choices) == 1 and scene.choices[0].next_scene in self.scenes:
                current_scene_id = scene.choices[0].next_scene
                continue
            reachable = self._reachable_encounter_scene_ids(current_scene_id, visited=set())
            if len(reachable) == 1:
                return next(iter(reachable))
            return current_scene_id
        return scene_id

    def _reachable_encounter_scene_ids(self, scene_id: str, visited: set[str]) -> set[str]:
        if scene_id in visited:
            return set()
        visited.add(scene_id)
        scene = self.scenes[scene_id]
        if scene.encounter is not None:
            return {scene_id}
        reachable: set[str] = set()
        for choice in scene.choices:
            if choice.next_scene is None or choice.next_scene not in self.scenes:
                continue
            reachable.update(self._reachable_encounter_scene_ids(choice.next_scene, visited.copy()))
        return reachable

    def _load_settings(self, path: Path) -> GameSettings:
        if not path.exists():
            return GameSettings()
        with path.open("r", encoding="utf-8") as config_file:
            payload = json.load(config_file)
        start_scene = payload.get("start_scene")
        rules = payload.get("rules", {})
        threshold = DEFAULT_DIRECTIONAL_AOE_CELL_COVERAGE_THRESHOLD
        if isinstance(rules, dict):
            configured = rules.get("directional_aoe_cell_coverage_threshold")
            if isinstance(configured, (int, float)):
                threshold = min(max(float(configured), 0.0), 1.0)
        return GameSettings(
            start_scene=start_scene if isinstance(start_scene, str) and start_scene else "welcome",
            rules_config=RulesConfig(directional_aoe_cell_coverage_threshold=threshold),
        )
