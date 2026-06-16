from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from .choice_resolver import ChoiceResolution, ChoiceResolver
from .models.actor import Actor
from .models.scene import Scene

SAVE_CHOICE_TEXT = "Save game"
LOAD_CHOICE_TEXT = "Load game"
EXIT_CHOICE_TEXT = "Exit game"


@dataclass
class SceneView:
    scene_id: str
    scene_text: str | None
    choices: list[str] = field(default_factory=list)


@dataclass
class TurnResult:
    scene: SceneView
    selected_index: int | None = None
    selected_choice_text: str | None = None
    messages: list[tuple[str, str]] = field(default_factory=list)
    next_scene_id: str | None = None
    scene_changed: bool = False
    should_exit: bool = False


class GameSession:
    def __init__(
        self,
        scenes: dict[str, Scene],
        player: Actor,
        choice_resolver: ChoiceResolver | None = None,
        start_scene_id: str = "welcome",
        game_dir: str | Path = "sample_game",
        save_dir: str | Path = "saves",
    ):
        self.scenes = scenes
        self.player = player
        self.choice_resolver = choice_resolver or ChoiceResolver()
        self.current_scene_id = start_scene_id
        self.start_scene_id = start_scene_id
        self._initial_player = deepcopy(player)
        self.game_dir = Path(game_dir)
        self.save_dir = Path(save_dir)

    @property
    def current_scene(self) -> Scene:
        return self.scenes[self.current_scene_id]

    def get_scene_view(self) -> SceneView:
        scene = self.current_scene
        return SceneView(
            scene_id=scene.id,
            scene_text=scene.text,
            choices=[
                choice.choice_text for choice in scene.choices
            ]
            + [SAVE_CHOICE_TEXT, LOAD_CHOICE_TEXT, EXIT_CHOICE_TEXT],
        )

    def choose(self, choice_index: int) -> TurnResult:
        scene = self.current_scene
        if choice_index == len(scene.choices):
            return self._save_game()
        if choice_index == len(scene.choices) + 1:
            return self._load_game()
        if choice_index == len(scene.choices) + 2:
            return self._exit_game()

        if not 0 <= choice_index < len(scene.choices):
            raise IndexError(
                f"Choice index {choice_index} is out of range for scene '{scene.id}'."
            )

        choice = scene.choices[choice_index]
        resolution = self.choice_resolver.resolve(scene, choice, actor=self.player)
        next_scene_id = resolution.next_scene_id or scene.id
        scene_changed = next_scene_id != scene.id
        if next_scene_id == self.start_scene_id and scene.id != self.start_scene_id:
            self.reset()
            next_scene_id = self.current_scene_id
            scene_changed = True
        else:
            self.current_scene_id = next_scene_id

        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=choice_index,
            selected_choice_text=choice.choice_text,
            messages=resolution.messages,
            next_scene_id=next_scene_id,
            scene_changed=scene_changed,
        )

    def reset(self) -> None:
        self.player = deepcopy(self._initial_player)
        self.choice_resolver = ChoiceResolver()
        self.current_scene_id = self.start_scene_id

    def _save_game(self) -> TurnResult:
        from .save import save_to_slot

        save_path = save_to_slot(self, self.save_dir, 1)
        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=len(self.current_scene.choices),
            selected_choice_text=SAVE_CHOICE_TEXT,
            messages=[("system", f"Game saved to {save_path}.")],
            next_scene_id=self.current_scene_id,
            scene_changed=False,
        )

    def _load_game(self) -> TurnResult:
        from .save import load_from_slot

        try:
            loaded = load_from_slot(self.save_dir, 1, self.game_dir)
        except FileNotFoundError:
            return TurnResult(
                scene=self.get_scene_view(),
                selected_index=len(self.current_scene.choices) + 1,
                selected_choice_text=LOAD_CHOICE_TEXT,
                messages=[("system", "No save file found in slot 1.")],
                next_scene_id=self.current_scene_id,
                scene_changed=False,
            )

        self.player = loaded.player
        self.choice_resolver = loaded.choice_resolver
        self.current_scene_id = loaded.current_scene_id
        self.start_scene_id = loaded.start_scene_id
        self._initial_player = deepcopy(loaded._initial_player)

        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=len(self.current_scene.choices) + 1,
            selected_choice_text=LOAD_CHOICE_TEXT,
            messages=[("system", "Game loaded from saves/slot_1.json.")],
            next_scene_id=self.current_scene_id,
            scene_changed=False,
        )

    def _exit_game(self) -> TurnResult:
        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=len(self.current_scene.choices) + 2,
            selected_choice_text=EXIT_CHOICE_TEXT,
            messages=[("system", "Exiting game.")],
            next_scene_id=self.current_scene_id,
            scene_changed=False,
            should_exit=True,
        )
