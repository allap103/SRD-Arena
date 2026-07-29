from copy import deepcopy
from dataclasses import dataclass

from ..domain.encounters.encounter import EncounterState
from ..domain.encounters.models import EncounterAction
from ..frontends.shared.combat import render_encounter_text
from ..domain.creatures import Creature
from ..domain.encounters import EncounterDefinition
from ..domain.equipment import Item
from ..domain.geometry import GeometryConfig
from ..frontends.shared.models import ActionView, SceneView, TurnResult

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
        player: Creature,
        creature_templates: dict[str, Creature] | None = None,
        item_templates: dict[str, Item] | None = None,
        start_scene_id: str = "goblin_encounter",
        control_mode: str = "default",
        automatic_action_limit: int | None = None,
        geometry_config: GeometryConfig | None = None,
    ):
        self.encounters = encounters
        self.player = player
        self.creature_templates = creature_templates or {player.id: player}
        self.item_templates = item_templates or {}
        self.start_scene_id = start_scene_id
        self.current_scene_id = start_scene_id
        self._initial_player = deepcopy(player)
        self.control_mode = control_mode
        self._automatic_action_limit = automatic_action_limit
        self.geometry_config = geometry_config or GeometryConfig()
        self.encounter_state: EncounterState | None = None
        self._encounter_actions: list[EncounterAction] = []
        self.pending_scene_transition: PendingSceneTransition | None = None

    @property
    def current_encounter(self) -> EncounterDefinition:
        return self.encounters[self.current_scene_id]

    @property
    def automatic_action_limit(self) -> int | None:
        return self._automatic_action_limit

    @automatic_action_limit.setter
    def automatic_action_limit(self, value: int | None) -> None:
        self._automatic_action_limit = value
        if self.encounter_state is not None:
            self.encounter_state.automatic_action_limit = value

    def start_encounter(self) -> Session:
        """Start the current encounter, including initiative and behavior setup."""
        encounter = self.current_encounter
        if (
            self.encounter_state is not None
            and self.encounter_state.encounter_id == encounter.id
        ):
            return self
        self.encounter_state = EncounterState.from_definition(
            encounter.id,
            encounter,
            self.player,
            self.creature_templates,
            self.item_templates,
            self.control_mode,
            self.geometry_config,
        )
        self.encounter_state.automatic_action_limit = self.automatic_action_limit
        self._encounter_actions = []
        return self

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
                scene_id=self.current_encounter.id,
                scene_text=self.pending_scene_transition.message,
                choices=[
                    CONTINUE_CHOICE_TEXT,
                    EXIT_CHOICE_TEXT,
                ],
                action_details=action_details + system_action_details,
            )

        if self.encounter_state is None:
            raise RuntimeError("Cannot build an encounter view before starting the encounter.")
        encounter = self.current_encounter
        scene_text = render_encounter_text(self.encounter_state, self.player)
        self._encounter_actions = self.encounter_state.actions.available(
            self.encounter_state.current_decision().actor_ref
        )
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

        choices = [action.label for action in action_details]
        system_action_details = self._system_action_details(len(choices))
        return SceneView(
            scene_id=encounter.id,
            scene_text=scene_text,
            choices=choices + [EXIT_CHOICE_TEXT],
            action_details=action_details + system_action_details,
        )

    def choose(self, choice_index: int) -> TurnResult:
        if self.pending_scene_transition is not None:
            if choice_index == 0:
                return self._continue_scene_transition()
            if choice_index == 1:
                return self._exit_game()
            raise IndexError("Choice index is out of range for the transition prompt.")

        if self.encounter_state is None:
            raise RuntimeError("Cannot choose an encounter action before starting the encounter.")
        action_count = len(self._encounter_actions)
        if choice_index == action_count:
            return self._exit_game()
        if self.encounter_state is not None:
            return self._choose_encounter(choice_index)
        if not 0 <= choice_index < action_count:
            raise IndexError(
                f"Choice index {choice_index} is out of range for encounter "
                f"'{self.current_encounter.id}'."
            )
        raise RuntimeError("No encounter is active.")

    def reset(self) -> None:
        self.player = deepcopy(self._initial_player)
        self.current_scene_id = self.start_scene_id
        self.pending_scene_transition = None
        self.encounter_state = None
        self._encounter_actions = []

    def _exit_game(self) -> TurnResult:
        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=len(self.get_scene_view().choices) - 1,
            selected_choice_text=EXIT_CHOICE_TEXT,
            selected_action_id="system-exit",
            messages=[("system", "Exiting srd_arena.")],
            next_scene_id=self.current_scene_id,
            scene_changed=False,
            should_exit=True,
        )

    def _choose_encounter(self, choice_index: int) -> TurnResult:
        if not 0 <= choice_index < len(self._encounter_actions):
            raise IndexError(
                f"Choice index {choice_index} is out of range for encounter "
                f"'{self.current_encounter.id}'."
            )
        if self.encounter_state is None:
            raise RuntimeError(
                "Encounter action requested without an active encounter."
            )
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
        if self.encounter_state is None:
            raise RuntimeError("Cannot perform an encounter action before starting the encounter.")
        if self.encounter_state is None:
            raise RuntimeError(
                "Encounter action requested without an active encounter."
            )
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
        progress = self.encounter_state.actions.perform(action)
        messages = progress.messages
        transition = progress.transition
        if self.player.get_health() <= 0 and self.current_encounter.defeat:
            transition = self.current_encounter.defeat.next_encounter_id

        scene_changed = False
        if transition is not None:
            scene_changed = self._apply_encounter_transition(transition)
            if self.pending_scene_transition is not None:
                messages = [
                    *messages,
                    ("system", self.pending_scene_transition.message),
                ]

        combat_state = (
            self.encounter_state.read_model.state_for(self.player)
            if self.encounter_state is not None
            else None
        )
        decision = (
            self.encounter_state.read_model.decision()
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

    def advance_until_input_required(self) -> TurnResult:
        if self.encounter_state is None:
            raise RuntimeError("Cannot advance automatically before starting the encounter.")
        if not self.encounter_state.requires_automatic_advance():
            raise RuntimeError(
                "Automatic advancement requested while external input is required."
            )

        progress = self.encounter_state.advance_until_next_decision(self.player)
        transition = progress.transition
        if self.player.get_health() <= 0 and self.current_encounter.defeat:
            transition = self.current_encounter.defeat.next_encounter_id

        scene_changed = False
        if transition is not None:
            scene_changed = self._apply_encounter_transition(transition)
            if self.pending_scene_transition is not None:
                progress.messages = [
                    *progress.messages,
                    ("system", self.pending_scene_transition.message),
                ]

        combat_state = (
            self.encounter_state.read_model.state_for(self.player)
            if self.encounter_state is not None
            else None
        )
        decision = (
            self.encounter_state.read_model.decision()
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

    def _clear_encounter_if_scene_changed(
        self, previous_scene_id: str, next_scene_id: str
    ) -> None:
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
        self.start_encounter()
        return TurnResult(
            scene=self.get_scene_view(),
            selected_index=0,
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
            and self.player.get_health() > 0
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
        self.start_encounter()
        return previous_scene_id != self.current_scene_id

    def _system_action_details(self, start_index: int) -> list[ActionView]:
        return [
            ActionView(
                index=start_index,
                id="system-exit",
                label=EXIT_CHOICE_TEXT,
                kind="system_exit",
                actor_ref="player",
                value=None,
            ),
        ]
