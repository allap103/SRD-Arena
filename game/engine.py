from pathlib import Path

from .game_logging import CHANNEL_ENGINE, get_game_logger
from .loaders import load_actor, load_item, load_scene
from .models.actor import Actor
from .models.item import Item
from .models.scene import Scene
from .scene_runner import SceneRunner
from .session import GameSession

GAME_DIR = Path("sample_game")
LOGGER = get_game_logger(CHANNEL_ENGINE)


class Game:
    scenes: dict[str, Scene]
    actors: list[Actor]
    items: list[Item]

    def __init__(self, directory: str = GAME_DIR, start_scene: str = "welcome"):
        self.scenes = self.load_scenes_from_directory(Path(directory) / "scenes")
        self.actors = self.load_actors_from_directory(Path(directory) / "actors")
        self.items = self.load_items_from_directory(Path(directory) / "items")
        self.start_scene = start_scene
        self.scene_runner = SceneRunner()

    def load_actors_from_directory(self, directory: str) -> list[Actor]:
        return [load_actor(path) for path in Path(directory).glob("*")]

    def load_items_from_directory(self, directory: str) -> list[Item]:
        return [load_item(path) for path in Path(directory).glob("*")]

    def load_scenes_from_directory(self, directory: str) -> dict[str, Scene]:
        return {
            scene.id: scene
            for scene in (load_scene(path) for path in Path(directory).glob("*"))
        }

    def get_actor(self, actor_id: str) -> Actor:
        for actor in self.actors:
            if actor.id == actor_id:
                return actor
        raise KeyError(f"Actor '{actor_id}' not found.")

    def create_session(self, player_actor_id: str = "player") -> GameSession:
        return GameSession(
            scenes=self.scenes,
            player=self.get_actor(player_actor_id),
            start_scene_id=self.start_scene,
        )

    def run(self):
        session = self.create_session()
        try:
            while True:
                self.scene_runner.run(session)
        except (KeyboardInterrupt, EOFError):
            LOGGER.info("You set the story aside for now. Thanks for playing.")
