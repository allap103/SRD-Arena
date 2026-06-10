from copy import deepcopy
from dataclasses import dataclass, field

from .choice_resolver import ChoiceResolution, ChoiceResolver
from .models.actor import Actor
from .models.scene import Scene


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


class GameSession:
    def __init__(
        self,
        scenes: dict[str, Scene],
        player: Actor,
        choice_resolver: ChoiceResolver | None = None,
        start_scene_id: str = "welcome",
    ):
        self.scenes = scenes
        self.player = player
        self.choice_resolver = choice_resolver or ChoiceResolver()
        self.current_scene_id = start_scene_id
        self.start_scene_id = start_scene_id
        self._initial_player = deepcopy(player)

    @property
    def current_scene(self) -> Scene:
        return self.scenes[self.current_scene_id]

    def get_scene_view(self) -> SceneView:
        scene = self.current_scene
        return SceneView(
            scene_id=scene.id,
            scene_text=scene.text,
            choices=[choice.choice_text for choice in scene.choices],
        )

    def choose(self, choice_index: int) -> TurnResult:
        scene = self.current_scene
        if not 0 <= choice_index < len(scene.choices):
            raise IndexError(f"Choice index {choice_index} is out of range for scene '{scene.id}'.")

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
