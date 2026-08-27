from copy import deepcopy
from dataclasses import dataclass

from srd_arena.domain.creatures import Creature
from srd_arena.domain.encounters import EncounterDefinition, EncounterOrchestrator
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.models import EncounterAction
from srd_arena.domain.equipment import Item
from srd_arena.domain.geometry import GeometryConfig
from srd_arena.engine.action_configuration import (
    configure_action as configure_engine_action,
)
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.queries import (
    ActionConfiguration,
    CONTINUE_CHOICE_TEXT,
    EXIT_CHOICE_TEXT,
    SessionRead,
)
from srd_arena.engine.session_queries import read_session


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
        encounter_orchestrator: EncounterOrchestrator | None = None,
    ):
        self.encounters = encounters
        self.creature_templates = creature_templates
        self.item_templates = item_templates or {}
        self.start_scene_id = start_scene_id
        self.current_scene_id = start_scene_id
        self._initial_creature_templates = deepcopy(creature_templates)
        self.automatic_action_limit = automatic_action_limit
        self.geometry_config = geometry_config or GeometryConfig()
        self.encounter_orchestrator = encounter_orchestrator or EncounterOrchestrator()
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

    def read(self) -> SessionRead:
        """Return the typed internal inputs for application observation."""

        return read_session(self)

    def choose(self, action_id: str) -> EngineOutcome:
        if self.pending_scene_transition is not None:
            if action_id == "system-continue-scene-transition":
                return self._continue_scene_transition()
            if action_id == "system-exit":
                return self._exit_game()
            raise KeyError(
                f"Action '{action_id}' is unavailable for the transition prompt."
            )

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

    def _exit_game(self) -> EngineOutcome:
        return EngineOutcome(
            selected_choice_text=EXIT_CHOICE_TEXT,
            selected_action_id="system-exit",
            messages=(("system", "Exiting srd_arena."),),
            scene_changed=False,
            should_exit=True,
        )
    def _choose_encounter(self, action_id: str) -> EngineOutcome:
        if self.encounter_state is None:
            raise RuntimeError(
                "Encounter action requested without an active encounter."
            )
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
    ) -> EngineOutcome:
        self._ensure_encounter_state()
        if self.encounter_state is None:
            raise RuntimeError(
                "Encounter action requested without an active encounter."
            )
        return self._apply_encounter_action(
            action,
            selected_choice_text=selected_choice_text or action.label,
        )

    def configure_action(
        self,
        action_id: str,
        configuration: ActionConfiguration,
    ) -> EngineOutcome:
        """Apply typed configuration to an advertised executable action."""

        return configure_engine_action(self, action_id, configuration)

    def _apply_encounter_action(
        self,
        action: EncounterAction,
        *,
        selected_choice_text: str,
    ) -> EngineOutcome:
        assert self.encounter_state is not None
        progress = self.encounter_orchestrator.submit(
            self.encounter_state,
            action,
        )
        messages = progress.messages
        transition = progress.transition

        scene_changed = False
        if transition is not None:
            scene_changed = self._apply_encounter_transition(transition)
            if self.pending_scene_transition is not None:
                messages = [
                    *messages,
                    ("system", self.pending_scene_transition.message),
                ]

        return EngineOutcome(
            selected_choice_text=selected_choice_text,
            selected_action_id=action.id,
            messages=tuple(messages),
            scene_changed=scene_changed,
            events=tuple(progress.events),
        )

    def advance_until_input_required(self) -> EngineOutcome:
        self._ensure_encounter_state()
        if self.encounter_state is None:
            raise RuntimeError("AI advancement requested without an active encounter.")
        if not self.encounter_state.requires_automatic_advance():
            raise RuntimeError(
                "AI advancement requested while no AI creature is active."
            )

        progress = self.encounter_orchestrator.advance(self.encounter_state)
        transition = progress.transition

        scene_changed = False
        if transition is not None:
            scene_changed = self._apply_encounter_transition(transition)
            if self.pending_scene_transition is not None:
                progress.messages = [
                    *progress.messages,
                    ("system", self.pending_scene_transition.message),
                ]

        return EngineOutcome(
            messages=tuple(progress.messages),
            scene_changed=scene_changed,
            events=tuple(progress.events),
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

    def _clear_encounter_if_scene_changed(
        self, previous_scene_id: str, next_scene_id: str
    ) -> None:
        if previous_scene_id != next_scene_id:
            self.encounter_state = None
            self._encounter_actions = []

    def _continue_scene_transition(self) -> EngineOutcome:
        pending = self.pending_scene_transition
        if pending is None:
            raise RuntimeError("Continue requested without a pending scene transition.")
        previous_scene_id = self.current_scene_id
        self.current_scene_id = pending.next_scene_id
        self.pending_scene_transition = None
        self.encounter_state = None
        self._encounter_actions = []
        self._ensure_encounter_state()
        return EngineOutcome(
            selected_choice_text=CONTINUE_CHOICE_TEXT,
            selected_action_id="system-continue-scene-transition",
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
