from copy import deepcopy
from pathlib import Path

from .choice_resolver import ChoiceResolver
from ..combat.encounter import (
    EncounterAction,
    EncounterSnapshot,
    EncounterState,
)
from ..models.actor import Actor
from ..models.item import Item
from ..presentation.models import ActionView, SceneView, TurnResult
from ..support.paths import SCENARIOS_ROOT
from ..models.rules_config import RulesConfig
from ..models.scene import Scene
from .rest import apply_rest

SHORT_REST_CHOICE_TEXT = "Short Rest"
LONG_REST_CHOICE_TEXT = "Long Rest"
SAVE_CHOICE_TEXT = "Save game"
LOAD_CHOICE_TEXT = "Load game"
EXIT_CHOICE_TEXT = "Exit game"


class GameSession:
    def __init__(
        self,
        scenes: dict[str, Scene],
        player: Actor,
        actor_templates: dict[str, Actor] | None = None,
        item_templates: dict[str, Item] | None = None,
        choice_resolver: ChoiceResolver | None = None,
        start_scene_id: str = "welcome",
        game_dir: str | Path = SCENARIOS_ROOT / "sample_game",
        save_dir: str | Path = "saves",
        control_mode: str = "default",
        ai_action_limit: int | None = None,
        rules_config: RulesConfig | None = None,
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
        self.control_mode = control_mode
        self.ai_action_limit = ai_action_limit
        self.rules_config = rules_config or RulesConfig()
        self.encounter_state: EncounterState | None = None
        self._encounter_actions: list[EncounterAction] = []

    @property
    def current_scene(self) -> Scene:
        return self.scenes[self.current_scene_id]

    def get_scene_view(self) -> SceneView:
        self._ensure_encounter_state()
        scene = self.current_scene
        scene_text = scene.text
        action_details = self._non_encounter_action_details()
        choices = [action.label for action in action_details]
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
        action_count = (
            len(self._encounter_actions)
            if self.encounter_state is not None
            else len(self._non_encounter_action_details())
        )
        if choice_index == action_count:
            return self._save_game()
        if choice_index == action_count + 1:
            return self._load_game()
        if choice_index == action_count + 2:
            return self._exit_game()
        if self.encounter_state is not None:
            return self._choose_encounter(choice_index)

        if not 0 <= choice_index < action_count:
            raise IndexError(
                f"Choice index {choice_index} is out of range for scene '{scene.id}'."
            )

        if choice_index == len(scene.choices):
            return self._take_rest("short_rest")
        if choice_index == len(scene.choices) + 1:
            return self._take_rest("long_rest")

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

    def _take_rest(self, rest_type: str) -> TurnResult:
        outcome = apply_rest(self.player, rest_type)
        if rest_type == "short_rest":
            selected_choice_text = SHORT_REST_CHOICE_TEXT
            selected_action_id = "system-short-rest"
            messages = [("system", "You take a short rest.")]
            if outcome["restored_resources"]:
                messages.append(
                    ("system", f"Recovered {outcome['restored_resources']} feature use(s).")
                )
            else:
                messages.append(("system", "No resources are recovered yet."))
            selected_index = len(self.current_scene.choices)
        else:
            selected_choice_text = LONG_REST_CHOICE_TEXT
            selected_action_id = "system-long-rest"
            messages = [("system", "You take a long rest.")]
            messages.append(("system", f"You recover {outcome['healed']} hit point(s)."))
            if outcome["restored_resources"]:
                messages.append(
                    ("system", f"Recovered {outcome['restored_resources']} feature use(s).")
                )
            selected_index = len(self.current_scene.choices) + 1

        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=selected_index,
            selected_choice_text=selected_choice_text,
            selected_action_id=selected_action_id,
            messages=messages,
            next_scene_id=self.current_scene_id,
            scene_changed=False,
        )

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
        self.control_mode = loaded.control_mode
        self.rules_config = loaded.rules_config
        if self.encounter_state is not None:
            self.encounter_state.ai_action_limit = self.ai_action_limit
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
        return self._apply_encounter_action(
            action,
            selected_index=choice_index,
            selected_choice_text=action.label,
        )

    def choose_encounter_action(
        self,
        action: EncounterAction,
        *,
        selected_choice_text: str | None = None,
    ) -> TurnResult:
        self._ensure_encounter_state()
        if self.encounter_state is None:
            raise RuntimeError("Encounter action requested without an active encounter.")
        return self._apply_encounter_action(
            action,
            selected_index=None,
            selected_choice_text=selected_choice_text or action.label,
        )

    def _apply_encounter_action(
        self,
        action: EncounterAction,
        *,
        selected_index: int | None,
        selected_choice_text: str,
    ) -> TurnResult:
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
            selected_index=selected_index,
            selected_choice_text=selected_choice_text,
            selected_action_id=action.id,
            messages=messages,
            next_scene_id=self.current_scene_id,
            scene_changed=scene_changed,
            events=progress.events,
            decision=decision,
            combat_state=combat_state,
        )

    def advance_ai(self) -> TurnResult:
        self._ensure_encounter_state()
        if self.encounter_state is None:
            raise RuntimeError("AI advancement requested without an active encounter.")
        if not self.encounter_state.needs_ai_advance():
            raise RuntimeError("AI advancement requested while no AI actor is active.")

        progress = self.encounter_state.advance_until_next_decision(self.player)
        transition = progress.transition
        if (
            self.player.get_health() <= 0
            and self.current_scene.encounter
            and self.current_scene.encounter.defeat
        ):
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
            messages=progress.messages,
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
            self.control_mode,
            self.rules_config,
        )
        self.encounter_state.ai_action_limit = self.ai_action_limit
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
            self.rules_config,
        )
        self.encounter_state.ai_action_limit = self.ai_action_limit

    def _non_encounter_action_details(self) -> list[ActionView]:
        scene_actions = [
            ActionView(
                index=index,
                id=f"scene-choice-{index}",
                label=choice.choice_text,
                kind="scene_choice",
                actor_ref="player",
                value=None,
            )
            for index, choice in enumerate(self.current_scene.choices)
        ]
        return scene_actions + [
            ActionView(
                index=len(scene_actions),
                id="system-short-rest",
                label=SHORT_REST_CHOICE_TEXT,
                kind="system_short_rest",
                actor_ref="player",
                value=None,
            ),
            ActionView(
                index=len(scene_actions) + 1,
                id="system-long-rest",
                label=LONG_REST_CHOICE_TEXT,
                kind="system_long_rest",
                actor_ref="player",
                value=None,
            ),
        ]

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
