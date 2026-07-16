from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from ..domain.combat.encounter import EncounterState
from ..domain.combat.models import EncounterAction, EncounterSnapshot
from ..frontends.shared.combat import render_encounter_text
from ..domain.creature import Creature
from ..domain.choice import Choice
from ..domain.item import Item
from ..domain.scene import Scene
from ..domain.rules.config import RulesConfig
from ..frontends.shared.models import ActionView, SceneView, TurnResult
from ..content.paths import SCENARIOS_ROOT

SAVE_CHOICE_TEXT = "Save game"
LOAD_CHOICE_TEXT = "Load game"
EXIT_CHOICE_TEXT = "Exit game"
CONTINUE_CHOICE_TEXT = "Continue"


@dataclass
class PendingSceneTransition:
    next_scene_id: str
    message: str


class Session:
    def __init__(
        self,
        scenes: dict[str, Scene],
        player: Creature,
        creature_templates: dict[str, Creature] | None = None,
        item_templates: dict[str, Item] | None = None,
        start_scene_id: str = "welcome",
        scenario_dir: str | Path = SCENARIOS_ROOT / "sample_game",
        save_dir: str | Path = "saves",
        control_mode: str = "default",
        ai_action_limit: int | None = None,
        rules_config: RulesConfig | None = None,
    ):
        self.scenes = scenes
        self.player = player
        self.creature_templates = creature_templates or {player.id: player}
        self.item_templates = item_templates or {}
        self.start_scene_id = start_scene_id
        self.current_scene_id = self._resolve_scene_id(start_scene_id)
        self._initial_player = deepcopy(player)
        self.scenario_dir = Path(scenario_dir)
        self.save_dir = Path(save_dir)
        self.control_mode = control_mode
        self.ai_action_limit = ai_action_limit
        self.rules_config = rules_config or RulesConfig()
        self.encounter_state: EncounterState | None = None
        self._encounter_actions: list[EncounterAction] = []
        self.pending_scene_transition: PendingSceneTransition | None = None

    @property
    def current_scene(self) -> Scene:
        return self.scenes[self.current_scene_id]

    def get_scene_view(self) -> SceneView:
        if self.pending_scene_transition is not None:
            action_details = [
                ActionView(
                    index=0,
                    id="system-continue-scene-transition",
                    label=CONTINUE_CHOICE_TEXT,
                    kind="system_continue_transition",
                    actor_ref="player",
                    value=None,
                )
            ]
            system_action_details = self._system_action_details(1)
            return SceneView(
                scene_id=self.current_scene.id,
                scene_text=(
                    self.current_scene.text
                    if self.encounter_state is not None
                    else self.pending_scene_transition.message
                ),
                choices=[CONTINUE_CHOICE_TEXT, SAVE_CHOICE_TEXT, LOAD_CHOICE_TEXT, EXIT_CHOICE_TEXT],
                action_details=action_details + system_action_details,
            )

        self._ensure_encounter_state()
        scene = self.current_scene
        if self.encounter_state is not None:
            scene_text = "\n\n".join(
                part
                for part in [scene.text, render_encounter_text(self.encounter_state, self.player)]
                if part
            )
            self._encounter_actions = self.encounter_state.available_actions(self.player)
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
        else:
            scene_text = scene.text
            action_details = self._scene_transition_action_details()

        choices = [action.label for action in action_details]
        system_action_details = self._system_action_details(len(choices))
        return SceneView(
            scene_id=scene.id,
            scene_text=scene_text,
            choices=choices + [SAVE_CHOICE_TEXT, LOAD_CHOICE_TEXT, EXIT_CHOICE_TEXT],
            action_details=action_details + system_action_details,
        )

    def choose(self, choice_index: int) -> TurnResult:
        if self.pending_scene_transition is not None:
            if choice_index == 0:
                return self._continue_scene_transition()
            if choice_index == 1:
                return self._save_game()
            if choice_index == 2:
                return self._load_game()
            if choice_index == 3:
                return self._exit_game()
            raise IndexError("Choice index is out of range for the transition prompt.")

        self._ensure_encounter_state()
        action_count = (
            len(self._encounter_actions)
            if self.encounter_state is not None
            else len(self._scene_transition_action_details())
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
                f"Choice index {choice_index} is out of range for scene '{self.current_scene.id}'."
            )
        return self._continue_scene()

    def reset(self) -> None:
        self.player = deepcopy(self._initial_player)
        self.current_scene_id = self._resolve_scene_id(self.start_scene_id)
        self.pending_scene_transition = None
        self.encounter_state = None
        self._encounter_actions = []

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
            loaded = load_from_slot(self.save_dir, 1, self.scenario_dir)
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
        self.current_scene_id = loaded.current_scene_id
        self.start_scene_id = loaded.start_scene_id
        self._initial_player = deepcopy(loaded._initial_player)
        self.creature_templates = loaded.creature_templates
        self.item_templates = loaded.item_templates
        self.encounter_state = loaded.encounter_state
        self.control_mode = loaded.control_mode
        self.rules_config = loaded.rules_config
        self.pending_scene_transition = loaded.pending_scene_transition
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
        assert self.encounter_state is not None
        progress = self.encounter_state.apply_action(self.player, action)
        messages = progress.messages
        transition = progress.transition
        if self.player.get_health() <= 0 and self.current_scene.encounter and self.current_scene.encounter.defeat:
            transition = self.current_scene.encounter.defeat.next_scene

        scene_changed = False
        if transition is not None:
            scene_changed = self._apply_encounter_transition(transition)
            if self.pending_scene_transition is not None:
                messages = [*messages, ("system", self.pending_scene_transition.message)]

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
            raise RuntimeError("AI advancement requested while no AI creature is active.")

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
            scene_changed = self._apply_encounter_transition(transition)
            if self.pending_scene_transition is not None:
                progress.messages = [
                    *progress.messages,
                    ("system", self.pending_scene_transition.message),
                ]

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
            self.player,
            self.creature_templates,
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
            self.creature_templates,
            self.item_templates,
            self.rules_config,
        )
        self.encounter_state.ai_action_limit = self.ai_action_limit

    def _continue_scene_transition(self) -> TurnResult:
        pending = self.pending_scene_transition
        if pending is None:
            raise RuntimeError("Continue requested without a pending scene transition.")
        previous_scene_id = self.current_scene_id
        self.current_scene_id = self._resolve_scene_id(pending.next_scene_id)
        self.pending_scene_transition = None
        self.encounter_state = None
        self._encounter_actions = []
        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=0,
            selected_choice_text=CONTINUE_CHOICE_TEXT,
            selected_action_id="system-continue-scene-transition",
            next_scene_id=self.current_scene_id,
            scene_changed=previous_scene_id != self.current_scene_id,
        )

    def _continue_scene(self) -> TurnResult:
        transition_target = self._scene_transition_target()
        if transition_target is None:
            raise RuntimeError(f"Scene '{self.current_scene.id}' does not expose a selectable transition.")
        previous_scene_id = self.current_scene_id
        next_scene_id = self._resolve_scene_id(transition_target)
        self.current_scene_id = next_scene_id
        self._clear_encounter_if_scene_changed(previous_scene_id, next_scene_id)
        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=0,
            selected_choice_text=CONTINUE_CHOICE_TEXT,
            selected_action_id="scene-continue",
            next_scene_id=self.current_scene_id,
            scene_changed=previous_scene_id != self.current_scene_id,
        )

    def _apply_encounter_transition(self, transition: str) -> bool:
        encounter = self.current_scene.encounter
        if (
            encounter is not None
            and encounter.victory is not None
            and transition == encounter.victory.next_scene
            and self.player.get_health() > 0
        ):
            self.pending_scene_transition = PendingSceneTransition(
                next_scene_id=transition,
                message=encounter.victory.message or "Victory! Press continue to proceed.",
            )
            self._encounter_actions = []
            return False

        previous_scene_id = self.current_scene_id
        self.current_scene_id = self._resolve_scene_id(transition)
        self.pending_scene_transition = None
        self.encounter_state = None
        self._encounter_actions = []
        return previous_scene_id != self.current_scene_id

    def _scene_transition_action_details(self) -> list[ActionView]:
        transition_target = self._scene_transition_target()
        if transition_target is None:
            return []
        return [
            ActionView(
                index=0,
                id="scene-continue",
                label=CONTINUE_CHOICE_TEXT,
                kind="scene_continue",
                actor_ref="player",
                value=transition_target,
            )
        ]

    def _scene_transition_choice(self) -> Choice | None:
        choices = self.current_scene.choices
        if not choices:
            return None
        if len(choices) > 1:
            transition_target = self._find_unique_reachable_encounter(self.current_scene.id)
            if transition_target is None:
                raise RuntimeError(
                    f"Scene '{self.current_scene.id}' still contains multiple narrative choices. "
                    "Remove branching story content or convert it to combat transitions."
                )
            return Choice(choice_text=CONTINUE_CHOICE_TEXT, next_scene=transition_target)
        return choices[0]

    def _scene_transition_target(self) -> str | None:
        transition_choice = self._scene_transition_choice()
        if transition_choice is None:
            return None
        return transition_choice.next_scene

    def _resolve_scene_id(self, scene_id: str) -> str:
        scene = self.scenes[scene_id]
        if scene.encounter is not None or len(scene.choices) <= 1:
            return scene_id
        next_scene_id = self._find_unique_reachable_encounter(scene_id)
        return next_scene_id or scene_id

    def _find_unique_reachable_encounter(self, scene_id: str) -> str | None:
        reachable = self._reachable_encounter_scene_ids(scene_id, visited=set())
        if len(reachable) == 1:
            return next(iter(reachable))
        return None

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
