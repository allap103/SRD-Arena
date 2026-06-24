from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from .choice_resolver import ChoiceResolver
from .encounter import CombatEvent, EncounterAction, EncounterSnapshot, EncounterState
from .models.actor import Actor
from .models.item import Item
from .models.scene import Scene

SAVE_CHOICE_TEXT = "Save game"
LOAD_CHOICE_TEXT = "Load game"
EXIT_CHOICE_TEXT = "Exit game"


@dataclass
class SceneView:
    scene_id: str
    scene_text: str | None
    choices: list[str] = field(default_factory=list)
    action_details: list["ActionView"] = field(default_factory=list)


@dataclass
class ActionView:
    index: int
    id: str
    label: str
    kind: str
    actor_ref: str
    value: str | int | None = None
    cost: dict[str, int] = field(default_factory=dict)
    source_trigger_id: str | None = None


@dataclass
class TurnResult:
    scene: SceneView
    selected_index: int | None = None
    selected_choice_text: str | None = None
    selected_action_id: str | None = None
    messages: list[tuple[str, str]] = field(default_factory=list)
    next_scene_id: str | None = None
    scene_changed: bool = False
    should_exit: bool = False
    events: list[CombatEvent] = field(default_factory=list)
    decision: dict[str, object] | None = None
    combat_state: dict[str, object] | None = None


class GameSession:
    def __init__(
        self,
        scenes: dict[str, Scene],
        player: Actor,
        actor_templates: dict[str, Actor] | None = None,
        item_templates: dict[str, Item] | None = None,
        choice_resolver: ChoiceResolver | None = None,
        start_scene_id: str = "welcome",
        game_dir: str | Path = "sample_game",
        save_dir: str | Path = "saves",
    ):
        self.scenes = scenes
        self.player = player
        self.actor_templates = actor_templates or {player.id: player}
        self.item_templates = item_templates or {}
        self.choice_resolver = choice_resolver or ChoiceResolver()
        self.current_scene_id = start_scene_id
        self.start_scene_id = start_scene_id
        self._initial_player = deepcopy(player)
        self.game_dir = Path(game_dir)
        self.save_dir = Path(save_dir)
        self.encounter_state: EncounterState | None = None
        self._encounter_actions: list[EncounterAction] = []

    @property
    def current_scene(self) -> Scene:
        return self.scenes[self.current_scene_id]

    def get_scene_view(self) -> SceneView:
        self._ensure_encounter_state()
        scene = self.current_scene
        scene_text = scene.text
        choices = [choice.choice_text for choice in scene.choices]
        action_details = [
                ActionView(
                    index=index,
                    id=f"scene-choice-{index}",
                    label=choice.choice_text,
                    kind="scene_choice",
                    actor_ref="player",
                    value=None,
                )
            for index, choice in enumerate(scene.choices)
        ]
        if self.encounter_state is not None:
            scene_text = "\n\n".join(
                part
                for part in [scene.text, self.encounter_state.render(self.player)]
                if part
            )
            self._encounter_actions = self.encounter_state.available_actions(self.player)
            choices = [action.label for action in self._encounter_actions]
            action_details = [
                ActionView(
                    index=index,
                    id=action.id,
                    label=action.label,
                    kind=action.kind,
                    actor_ref=action.actor_ref,
                    value=action.value,
                    cost={
                        "movement": action.cost.movement,
                        "action": action.cost.action,
                        "bonus_action": action.cost.bonus_action,
                        "reaction": action.cost.reaction,
                    },
                    source_trigger_id=action.source_trigger_id,
                )
                for index, action in enumerate(self._encounter_actions)
            ]
        system_action_details = self._system_action_details(len(choices))
        return SceneView(
            scene_id=scene.id,
            scene_text=scene_text,
            choices=choices + [SAVE_CHOICE_TEXT, LOAD_CHOICE_TEXT, EXIT_CHOICE_TEXT],
            action_details=action_details + system_action_details,
        )

    def choose(self, choice_index: int) -> TurnResult:
        self._ensure_encounter_state()
        scene = self.current_scene
        action_count = len(self._encounter_actions) if self.encounter_state is not None else len(scene.choices)
        if choice_index == action_count:
            return self._save_game()
        if choice_index == action_count + 1:
            return self._load_game()
        if choice_index == action_count + 2:
            return self._exit_game()
        if self.encounter_state is not None:
            return self._choose_encounter(choice_index)

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
            self._clear_encounter_if_scene_changed(scene.id, next_scene_id)

        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=choice_index,
            selected_choice_text=choice.choice_text,
            selected_action_id=f"scene-choice-{choice_index}",
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
            selected_index=len(self.get_scene_view().choices) - 3,
            selected_choice_text=SAVE_CHOICE_TEXT,
            selected_action_id="system-save",
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
                selected_index=len(self.get_scene_view().choices) - 2,
                selected_choice_text=LOAD_CHOICE_TEXT,
                selected_action_id="system-load",
                messages=[("system", "No save file found in slot 1.")],
                next_scene_id=self.current_scene_id,
                scene_changed=False,
            )

        self.player = loaded.player
        self.choice_resolver = loaded.choice_resolver
        self.current_scene_id = loaded.current_scene_id
        self.start_scene_id = loaded.start_scene_id
        self._initial_player = deepcopy(loaded._initial_player)
        self.actor_templates = loaded.actor_templates
        self.item_templates = loaded.item_templates
        self.encounter_state = loaded.encounter_state
        self._encounter_actions = []
        self._ensure_encounter_state()

        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=len(self.get_scene_view().choices) - 2,
            selected_choice_text=LOAD_CHOICE_TEXT,
            selected_action_id="system-load",
            messages=[("system", "Game loaded from saves/slot_1.json.")],
            next_scene_id=self.current_scene_id,
            scene_changed=False,
        )

    def _exit_game(self) -> TurnResult:
        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=len(self.get_scene_view().choices) - 1,
            selected_choice_text=EXIT_CHOICE_TEXT,
            selected_action_id="system-exit",
            messages=[("system", "Exiting game.")],
            next_scene_id=self.current_scene_id,
            scene_changed=False,
            should_exit=True,
        )

    def _choose_encounter(self, choice_index: int) -> TurnResult:
        if not 0 <= choice_index < len(self._encounter_actions):
            raise IndexError(
                f"Choice index {choice_index} is out of range for encounter scene '{self.current_scene.id}'."
            )

        if self.encounter_state is None:
            raise RuntimeError("Encounter action requested without an active encounter.")

        action = self._encounter_actions[choice_index]
        progress = self.encounter_state.apply_action(self.player, action)
        messages = progress.messages
        transition = progress.transition
        if self.player.get_health() <= 0 and self.current_scene.encounter and self.current_scene.encounter.defeat:
            transition = self.current_scene.encounter.defeat.next_scene

        scene_changed = False
        if transition is not None:
            previous_scene_id = self.current_scene_id
            self.current_scene_id = transition
            self.encounter_state = None
            self._encounter_actions = []
            scene_changed = previous_scene_id != transition

        combat_state = (
            self.encounter_state.export_state(self.player)
            if self.encounter_state is not None
            else None
        )
        decision = (
            self.encounter_state.export_decision()
            if self.encounter_state is not None
            else None
        )
        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=choice_index,
            selected_choice_text=action.label,
            selected_action_id=action.id,
            messages=messages,
            next_scene_id=self.current_scene_id,
            scene_changed=scene_changed,
            events=progress.events,
            decision=decision,
            combat_state=combat_state,
        )

    def _ensure_encounter_state(self) -> None:
        scene = self.current_scene
        if scene.encounter is None:
            self.encounter_state = None
            self._encounter_actions = []
            return
        if self.encounter_state is not None and self.encounter_state.scene_id == scene.id:
            return
        self.encounter_state = EncounterState.from_definition(
            scene.id,
            scene.encounter,
            self.actor_templates,
            self.item_templates,
        )
        self._encounter_actions = []

    def _clear_encounter_if_scene_changed(self, previous_scene_id: str, next_scene_id: str) -> None:
        if previous_scene_id != next_scene_id:
            self.encounter_state = None
            self._encounter_actions = []

    def get_encounter_snapshot(self) -> EncounterSnapshot | None:
        self._ensure_encounter_state()
        if self.encounter_state is None:
            return None
        return self.encounter_state.snapshot()

    def restore_encounter_snapshot(self, snapshot: EncounterSnapshot | None) -> None:
        self.encounter_state = None
        self._encounter_actions = []
        if snapshot is None:
            return
        scene = self.scenes.get(snapshot.scene_id)
        if scene is None or scene.encounter is None:
            raise ValueError(f"Encounter scene '{snapshot.scene_id}' does not exist.")
        self.encounter_state = EncounterState.from_snapshot(
            scene.encounter,
            snapshot,
            self.actor_templates,
            self.item_templates,
        )

    def _system_action_details(self, start_index: int) -> list[ActionView]:
        return [
            ActionView(
                index=start_index,
                id="system-save",
                label=SAVE_CHOICE_TEXT,
                kind="system_save",
                actor_ref="player",
                value=None,
            ),
            ActionView(
                index=start_index + 1,
                id="system-load",
                label=LOAD_CHOICE_TEXT,
                kind="system_load",
                actor_ref="player",
                value=None,
            ),
            ActionView(
                index=start_index + 2,
                id="system-exit",
                label=EXIT_CHOICE_TEXT,
                kind="system_exit",
                actor_ref="player",
                value=None,
            ),
        ]
