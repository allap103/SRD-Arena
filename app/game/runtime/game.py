from pathlib import Path
import json
from dataclasses import dataclass, field

from ..support.logging import CHANNEL_ENGINE, get_game_logger
from ..story.scene_runner import SceneRunner
from ..content.loaders import (
    load_actor,
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
from ..models.actor import Actor
from ..models.item import Item
from ..models.rules_config import (
    DEFAULT_DIRECTIONAL_AOE_CELL_COVERAGE_THRESHOLD,
    RulesConfig,
)
from ..models.scene import Scene
from ..support.paths import SCENARIOS_ROOT, SYSTEM_CONTENT_ROOT
from .session import GameSession

GAME_DIR = SCENARIOS_ROOT / "sample_game"
GAME_SYSTEM_DIR = SYSTEM_CONTENT_ROOT
LOGGER = get_game_logger(CHANNEL_ENGINE)


@dataclass(frozen=True)
class GameSettings:
    start_scene: str = "welcome"
    rules_config: RulesConfig = field(default_factory=RulesConfig)


class Game:
    scenes: dict[str, Scene]
    actors: list[Actor]
    items: list[Item]
    rules_config: RulesConfig

    def __init__(
        self,
        directory: str | Path = GAME_DIR,
        start_scene: str | None = None,
        system_directory: str | Path = GAME_SYSTEM_DIR,
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
        self.actors = self.load_actors_from_directory(self.directory)
        self.items = self._merge_items(
            load_system_items(self.system_directory),
            self.load_items_from_directory(self.directory / "items"),
        )
        self.start_scene = start_scene or settings.start_scene
        self.control_mode = control_mode
        self.scene_runner = SceneRunner()

    def load_actors_from_directory(self, directory: str | Path) -> list[Actor]:
        actor_dir = Path(directory) / "actors"
        return [
            load_actor(
                path,
                self.stat_blocks,
                self.class_blocks,
                self.custom_stat_blocks,
                self.optional_feature_blocks,
                self.subclass_blocks,
                self.spell_catalog,
            )
            for path in actor_dir.glob("*")
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

    def get_actor(self, actor_id: str) -> Actor:
        for actor in self.actors:
            if actor.id == actor_id:
                return actor
        raise KeyError(f"Actor '{actor_id}' not found.")

    def create_session(
        self,
        player_actor_id: str = "player",
        control_mode: str | None = None,
    ) -> GameSession:
        return GameSession(
            scenes=self.scenes,
            player=self.get_actor(player_actor_id),
            actor_templates={actor.id: actor for actor in self.actors},
            item_templates={item.id: item for item in self.items},
            start_scene_id=self.start_scene,
            game_dir=self.directory,
            control_mode=control_mode or self.control_mode,
            rules_config=self.rules_config,
        )

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

    def run(self):
        session = self.create_session()
        try:
            while True:
                if not self.scene_runner.run(session):
                    break
        except (KeyboardInterrupt, EOFError):
            LOGGER.info("You set the story aside for now. Thanks for playing.")
