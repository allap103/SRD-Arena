"""Own a running game's mutable state and execute application requests."""

from copy import deepcopy
from dataclasses import dataclass

from srd_arena.domain.creatures import Creature
from srd_arena.domain.encounters import EncounterDefinition, EncounterOrchestrator
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.equipment import Item
from srd_arena.domain.geometry import GeometryConfig
from srd_arena.domain.rolls.randomness import DiceRoller
from srd_arena.engine.action_configuration import (
    configure_action as configure_engine_action,
)
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.queries import (
    CONTINUE_CHOICE_TEXT,
    EXIT_CHOICE_TEXT,
    ActionConfiguration,
    SessionRead,
)
from srd_arena.engine.session_queries import read_session


@dataclass
class PendingSceneTransition:
    """Hold a completed scene's destination until the client acknowledges it."""

    next_scene_id: str
    message: str


class Session:
    """Coordinate content definitions and mutable state for one running game.

    The session is the engine façade used by the application layer. It creates
    encounter state lazily, advertises currently executable choices, and sends
    accepted actions through the domain orchestrator. Presentation state and
    user-interface concerns remain outside it.
    """

    def __init__(
        self,
        encounters: dict[str, EncounterDefinition],
        creature_templates: dict[str, Creature],
        item_templates: dict[str, Item] | None = None,
        start_scene_id: str = "goblin_encounter",
        pace_automatic_actions: bool = False,
        geometry_config: GeometryConfig | None = None,
        encounter_orchestrator: EncounterOrchestrator | None = None,
        dice: DiceRoller | None = None,
    ):
        self.encounters = encounters
        self.creature_templates = creature_templates
        self.item_templates = item_templates or {}
        self.start_scene_id = start_scene_id
        self.current_scene_id = start_scene_id
        self._initial_creature_templates = deepcopy(creature_templates)
        self.pace_automatic_actions = pace_automatic_actions
        self.geometry_config = geometry_config or GeometryConfig()
        self.encounter_orchestrator = encounter_orchestrator or EncounterOrchestrator()
        self._dice = dice or DiceRoller()
        self.encounter_state: EncounterState | None = None
        self._encounter_actions: list[EncounterAction] = []
        self.pending_scene_transition: PendingSceneTransition | None = None

    @property
    def _current_encounter(self) -> EncounterDefinition:
        """Return the authored definition for the active scene.

        >>> from srd_arena.domain.geometry import Grid
        >>> encounter = EncounterDefinition("demo", Grid(1, 1))
        >>> Session({"demo": encounter}, {}, start_scene_id="demo")._current_encounter is encounter
        True
        """
        return self.encounters[self.current_scene_id]

    def read(self) -> SessionRead:
        """Return the typed internal inputs for application observation.

        >>> from srd_arena.domain.geometry import Grid
        >>> session = Session({"demo": EncounterDefinition("demo", Grid(1, 1))}, {}, start_scene_id="demo")
        >>> session.pending_scene_transition = PendingSceneTransition("next", "Victory!")
        >>> session.read().scene_text
        'Victory!'
        """

        return read_session(self)

    def choose(self, action_id: str) -> EngineOutcome:
        """Execute one action advertised by the current engine read.

        System exit remains available at an encounter decision point.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> session = Session({"demo": EncounterDefinition("demo", Grid(1, 1))}, {}, start_scene_id="demo")
        >>> session.encounter_state = Mock(encounter_id="demo")
        >>> outcome = session.choose("system-exit")
        >>> (outcome.selected_action_id, outcome.should_exit)
        ('system-exit', True)
        """
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
        """Restore the session to its initially loaded content and scene.

        >>> from srd_arena.domain.geometry import Grid
        >>> session = Session({"demo": EncounterDefinition("demo", Grid(1, 1))}, {}, start_scene_id="demo")
        >>> session.current_scene_id = "later"
        >>> session.reset()
        >>> (session.current_scene_id, session.encounter_state)
        ('demo', None)
        """
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
                f"'{self._current_encounter.id}'."
            )
        return self._apply_encounter_action(
            action,
            selected_choice_text=action.label,
        )

    def configure_action(
        self,
        action_id: str,
        configuration: ActionConfiguration,
    ) -> EngineOutcome:
        """Apply typed configuration to an advertised executable action.

        Configuration is accepted only for an action from the latest read.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> from srd_arena.engine.queries import ActionAim
        >>> session = Session({"demo": EncounterDefinition("demo", Grid(1, 1))}, {}, start_scene_id="demo")
        >>> session.encounter_state = Mock(encounter_id="demo")
        >>> session.configure_action("missing", ActionAim(1, 1))
        Traceback (most recent call last):
        ...
        KeyError: "Action 'missing' is unavailable."
        """

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
        """Advance automatic controllers until an external decision is needed.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
        >>> from srd_arena.domain.geometry import Grid
        >>> orchestrator = Mock()
        >>> orchestrator.advance.return_value = EncounterProgress(messages=[("Goblin", "Waits")])
        >>> session = Session({"demo": EncounterDefinition("demo", Grid(1, 1))}, {},
        ...     start_scene_id="demo", encounter_orchestrator=orchestrator)
        >>> session.encounter_state = Mock(
        ...     encounter_id="demo", requires_automatic_advance=Mock(return_value=True))
        >>> session.advance_until_input_required().messages
        (('Goblin', 'Waits'),)
        """
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
        encounter = self._current_encounter
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
            self._dice,
        )
        self.encounter_state.pace_automatic_actions = self.pace_automatic_actions
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
        encounter = self._current_encounter
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
