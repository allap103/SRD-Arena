from pathlib import Path

from .models.actor import Actor
from .models.item import Item
from .models.scene import Scene

GAME_DIR = Path("sample_game")


class Game:
    scenes: dict[str, Scene]
    actors: list[Actor]
    items: list[Item]

    def __init__(self, directory: str = GAME_DIR, start_scene: str = "welcome"):
        self.scenes = self.load_scenes_from_directory(Path(directory) / "scenes")
        self.actors = self.load_actors_from_directory(Path(directory) / "actors")
        self.start_scene = start_scene

    def load_actors_from_directory(self, directory: str) -> list[Actor]:
        return []

    def load_scenes_from_directory(self, directory: str) -> dict[str, Scene]:
        return {
            scene.id: scene
            for scene in (Scene.from_file(path) for path in Path(directory).glob("*"))
        }

    def run(self):
        current_scene = self.scenes[self.start_scene]
        try:
            while True:
                next_id = current_scene.run()
                current_scene = self.scenes[next_id]
        except (KeyboardInterrupt, EOFError):
            print("\n\nYou set the story aside for now. Thanks for playing.")
