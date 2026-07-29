from copy import deepcopy
from dataclasses import dataclass

from srd_arena.domain.creatures import Creature
from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.models import EncounterAction
from srd_arena.domain.equipment import Item
from srd_arena.domain.geometry import GeometryConfig
from .models import ActionView, SceneView, TurnResult

EXIT_CHOICE_TEXT = "Exit game"
CONTINUE_CHOICE_TEXT = "Continue"


@dataclass
class PendingSceneTransition:
    next_scene_id: str
    message: str


class Session:
    def __init__(
        self,
        encounters: dict[str, EncounterDefinition],
        creature_templates: dict[str, Creature],
        item_templates: dict[str, Item] | None = None,
        start_scene_id: str = "goblin_encounter",
        automatic_action_limit: int | None = None,
        geometry_config: GeometryConfig | None = None,
    ):
        self.encounters = encounters
        self.creature_templates = creature_templates
        self.item_templates = item_templates or {}
        self.start_scene_id = start_scene_id
        self.current_scene_id = start_scene_id
        self._initial_creature_templates = deepcopy(creature_templates)
        self.automatic_action_limit = automatic_action_limit
        self.geometry_config = geometry_config or GeometryConfig()
        self.encounter_state: EncounterState | None = None
        self._encounter_actions: list[EncounterAction] = []
        self.pending_scene_transition: PendingSceneTransition | None = None

    @property
    def decision_creature(self) -> Creature:
        self._ensure_encounter_state()
        assert self.encounter_state is not None
        return self.encounter_state.active_creature_state.creature

    @property
    def current_encounter(self) -> EncounterDefinition:
        return self.encounters[self.current_scene_id]

    def get_scene_view(self) -> SceneView:
        if self.pending_scene_transition is not None:
            action_details = [
                ActionView(
                    id="system-continue-scene-transition",
                    label=CONTINUE_CHOICE_TEXT,
                    kind="system_continue_transition",
                    creature_ref=self._system_action_creature_ref(),
                    value=None,
                )
            ]
            system_action_details = self._system_action_details()
            return SceneView(
                scene_id=self.current_encounter.id,
                scene_text=self.pending_scene_transition.message,
                action_details=action_details + system_action_details,
            )

        self._ensure_encounter_state()
        encounter = self.current_encounter
        assert self.encounter_state is not None
        self._encounter_actions = self.encounter_state.available_actions()
        action_ids = [action.id for action in self._encounter_actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("Available encounter action IDs must be unique.")
        action_details = [
                ActionView(
                    id=action.id,
                    label=action.label,
                    kind=action.kind,
                    creature_ref=action.creature_ref,
                    value=action.value,
                    cost={
                        "movement": action.cost.movement,
                        "action": action.cost.action,
                        "bonus_action": action.cost.bonus_action,
                        "reaction": action.cost.reaction,
                    },
                    source_trigger_id=action.source_trigger_id,
                    preferred_attack_type=action.preferred_attack_type,
                    preferred_attack_name=action.preferred_attack_name,
                )
            for action in self._encounter_actions
        ]

        system_action_details = self._system_action_details()
        return SceneView(
            scene_id=encounter.id,
            scene_text=None,
            action_details=action_details + system_action_details,
        )

    def choose(self, action_id: str) -> TurnResult:
        if self.pending_scene_transition is not None:
            if action_id == "system-continue-scene-transition":
                return self._continue_scene_transition()
            if action_id == "system-exit":
                return self._exit_game()
            raise KeyError(f"Action '{action_id}' is unavailable for the transition prompt.")

        self._ensure_encounter_state()
        if action_id == "system-exit":
            return self._exit_game()
        if self.encounter_state is not None:
            return self._choose_encounter(action_id)
        raise RuntimeError("No encounter is active.")

    def reset(self) -> None:
        self.creature_templates = deepcopy(self._initial_creature_templates)
        self.current_scene_id = self.start_scene_id
        self.pending_scene_transition = None
        self.encounter_state = None
        self._encounter_actions = []

    def _exit_game(self) -> TurnResult:
        return TurnResult(
            scene=self.get_scene_view(),
            selected_choice_text=EXIT_CHOICE_TEXT,
            selected_action_id="system-exit",
            messages=[("system", "Exiting srd_arena.")],
            next_scene_id=self.current_scene_id,
            scene_changed=False,
            should_exit=True,
        )

    def _choose_encounter(self, action_id: str) -> TurnResult:
        if self.encounter_state is None:
            raise RuntimeError("Encounter action requested without an active encounter.")
        action = next(
            (action for action in self._encounter_actions if action.id == action_id),
            None,
        )
        if action is None:
            raise KeyError(
                f"Action '{action_id}' is unavailable for encounter "
                f"'{self.current_encounter.id}'."
            )
        return self._apply_encounter_action(
            action,
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
            selected_choice_text=selected_choice_text or action.label,
        )

    def _apply_encounter_action(
        self,
        action: EncounterAction,
        *,
        selected_choice_text: str,
    ) -> TurnResult:
        assert self.encounter_state is not None
        progress = self.encounter_state.apply_action(action)
        messages = progress.messages
        transition = progress.transition

        scene_changed = False
        if transition is not None:
            scene_changed = self._apply_encounter_transition(transition)
            if self.pending_scene_transition is not None:
                messages = [*messages, ("system", self.pending_scene_transition.message)]

        combat_state = (
            self.encounter_state.export_state()
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
            selected_choice_text=selected_choice_text,
            selected_action_id=action.id,
            messages=messages,
            next_scene_id=self.current_scene_id,
            scene_changed=scene_changed,
            events=progress.events,
            decision=decision,
            combat_state=combat_state,
        )

    def advance_until_input_required(self) -> TurnResult:
        self._ensure_encounter_state()
        if self.encounter_state is None:
            raise RuntimeError("AI advancement requested without an active encounter.")
        if not self.encounter_state.requires_automatic_advance():
            raise RuntimeError("AI advancement requested while no AI creature is active.")

        progress = self.encounter_state.advance_until_next_decision()
        transition = progress.transition

        scene_changed = False
        if transition is not None:
            scene_changed = self._apply_encounter_transition(transition)
            if self.pending_scene_transition is not None:
                progress.messages = [
                    *progress.messages,
                    ("system", self.pending_scene_transition.message),
                ]

        combat_state = (
            self.encounter_state.export_state()
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
        encounter = self.current_encounter
        if (
            self.encounter_state is not None
            and self.encounter_state.encounter_id == encounter.id
        ):
            return
        self.encounter_state = EncounterState.from_definition(
            encounter.id,
            encounter,
            self.creature_templates,
            self.item_templates,
            self.geometry_config,
        )
        self.encounter_state.automatic_action_limit = self.automatic_action_limit
        self._encounter_actions = []

    def _clear_encounter_if_scene_changed(self, previous_scene_id: str, next_scene_id: str) -> None:
        if previous_scene_id != next_scene_id:
            self.encounter_state = None
            self._encounter_actions = []

    def _continue_scene_transition(self) -> TurnResult:
        pending = self.pending_scene_transition
        if pending is None:
            raise RuntimeError("Continue requested without a pending scene transition.")
        previous_scene_id = self.current_scene_id
        self.current_scene_id = pending.next_scene_id
        self.pending_scene_transition = None
        self.encounter_state = None
        self._encounter_actions = []
        return TurnResult(
            scene=self.get_scene_view(),
            selected_choice_text=CONTINUE_CHOICE_TEXT,
            selected_action_id="system-continue-scene-transition",
            next_scene_id=self.current_scene_id,
            scene_changed=previous_scene_id != self.current_scene_id,
        )

    def _apply_encounter_transition(self, transition: str) -> bool:
        encounter = self.current_encounter
        if (
            encounter is not None
            and encounter.victory is not None
            and transition == encounter.victory.next_encounter_id
        ):
            self.pending_scene_transition = PendingSceneTransition(
                next_scene_id=transition,
                message="Victory! Press continue to proceed.",
            )
            self._encounter_actions = []
            return False

        previous_scene_id = self.current_scene_id
        self.current_scene_id = transition
        self.pending_scene_transition = None
        self.encounter_state = None
        self._encounter_actions = []
        return previous_scene_id != self.current_scene_id

    def _system_action_details(self) -> list[ActionView]:
        return [
            ActionView(
                id="system-exit",
                label=EXIT_CHOICE_TEXT,
                kind="system_exit",
                creature_ref=self._system_action_creature_ref(),
                value=None,
            ),
        ]

    def _system_action_creature_ref(self) -> str:
        if self.encounter_state is None:
            return ""
        return self.encounter_state.current_decision().creature_ref
