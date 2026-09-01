"""Own mutable game state and expose the frontend-neutral engine API."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass

from srd_arena.domain.encounters import EncounterDefinition, EncounterOrchestrator
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.rolls.randomness import DiceRoller
from srd_arena.engine.action_configuration import (
    configure_action as configure_engine_action,
)
from srd_arena.engine.commands import CommandResult, GameCommand, GameUpdate
from srd_arena.engine.interactions import execute_game_command, game_update
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.observations import GameObservation, observe_session
from srd_arena.engine.queries import (
    EXIT_CHOICE_TEXT,
    RESTART_CHOICE_TEXT,
    ActionConfiguration,
    SessionRead,
)
from srd_arena.engine.session_queries import read_session


@dataclass
class PendingEncounterCompletion:
    """Hold a completed encounter until the client chooses what to do next."""

    message: str


class Session:
    """Coordinate content definitions and mutable state for one running game.

    The session is the public engine façade used by driving adapters. It creates
    encounter state lazily, validates frontend-neutral commands, advertises
    immutable observations, and sends accepted actions through the domain
    orchestrator. Presentation state and user-interface concerns remain outside
    it.
    """

    def __init__(
        self,
        encounter: EncounterDefinition,
        dice: DiceRoller | None = None,
    ):
        self.encounter = encounter
        self.creature_templates = {
            creature.id: creature for creature in encounter.creatures
        }
        self.item_templates = {item.id: item for item in encounter.items}
        self._initial_creature_templates = deepcopy(self.creature_templates)
        self.geometry_config = encounter.geometry_config
        self.encounter_orchestrator = EncounterOrchestrator()
        self._dice = dice or DiceRoller()
        self.encounter_state: EncounterState | None = None
        self._encounter_actions: list[EncounterAction] = []
        self.pending_encounter_completion: PendingEncounterCompletion | None = None

    def read(self) -> SessionRead:
        """Return typed internal inputs used to construct an observation.

        >>> from srd_arena.domain.geometry import Grid
        >>> encounter = EncounterDefinition("demo", Grid(1, 1))
        >>> session = Session(encounter)
        >>> session.pending_encounter_completion = PendingEncounterCompletion(
        ...     "Encounter complete"
        ... )
        >>> session.read().completion_message
        'Encounter complete'
        """

        return read_session(self)

    def observe(self) -> GameObservation:
        """Return an immutable snapshot of the current decision point.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.queries import SessionRead
        >>> session = Session.__new__(Session)
        >>> session.read = Mock(return_value=SessionRead(
        ...     "demo", (), None, None, (), {}, {}, {}, False
        ... ))
        >>> session.observe().scene.scene_id
        'demo'
        """

        return observe_session(self)

    def execute(self, command: GameCommand) -> CommandResult:
        """Validate and execute one frontend-neutral interaction command.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.commands import SelectAction
        >>> from srd_arena.engine.queries import SessionRead
        >>> session = Session.__new__(Session)
        >>> session.read = Mock(return_value=SessionRead(
        ...     "demo", (), None, None, (), {}, {}, {}, False
        ... ))
        >>> session.execute(SelectAction("wait", "old")).failure.code
        'stale_decision'
        """

        return execute_game_command(self, command)

    def choose(self, action_id: str) -> EngineOutcome:
        """Execute one action advertised by the current engine read.

        System exit remains available at an encounter decision point.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> encounter = EncounterDefinition("demo", Grid(1, 1))
        >>> session = Session(encounter)
        >>> session.encounter_state = Mock(encounter_id="demo")
        >>> outcome = session.choose("system-exit")
        >>> (outcome.selected_action_id, outcome.should_exit)
        ('system-exit', True)
        """
        if self.pending_encounter_completion is not None:
            if action_id == "system-restart-encounter":
                return self._restart_encounter()
            if action_id == "system-exit":
                return self._exit_game()
            raise KeyError(
                f"Action '{action_id}' is unavailable for the completion prompt."
            )

        self._ensure_encounter_state()
        if action_id == "system-exit":
            return self._exit_game()
        if self.encounter_state is not None:
            return self._choose_encounter(action_id)
        raise RuntimeError("No encounter is active.")

    def reset(self) -> GameObservation:
        """Restore the session to its initially loaded content and scene.

        A seeded session also rewinds its private dice stream, so repeating the
        same decisions after reset produces the same random outcomes.

        >>> from srd_arena.domain.geometry import Grid
        >>> encounter = EncounterDefinition("demo", Grid(1, 1))
        >>> session = Session(encounter)
        >>> from unittest.mock import Mock
        >>> session.observe = Mock(return_value=None)
        >>> session.reset()
        >>> session.encounter_state is None
        True
        """
        self._restore_initial_state()
        return self.observe()

    def _exit_game(self) -> EngineOutcome:
        return EngineOutcome(
            selected_choice_text=EXIT_CHOICE_TEXT,
            selected_action_id="system-exit",
            messages=(("system", "Exiting srd_arena."),),
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
                f"'{self.encounter.id}'."
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
        >>> encounter = EncounterDefinition("demo", Grid(1, 1))
        >>> session = Session(encounter)
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
        if progress.completed:
            self._complete_encounter()
            if self.pending_encounter_completion is not None:
                messages = [
                    *messages,
                    ("system", self.pending_encounter_completion.message),
                ]

        return EngineOutcome(
            selected_choice_text=selected_choice_text,
            selected_action_id=action.id,
            messages=tuple(messages),
            events=tuple(progress.events),
        )

    def advance_until_input_required(self) -> GameUpdate:
        """Advance automatic controllers until an external decision is needed.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
        >>> from srd_arena.domain.geometry import Grid
        >>> orchestrator = Mock()
        >>> orchestrator.advance.return_value = EncounterProgress(messages=[("Goblin", "Waits")])
        >>> encounter = EncounterDefinition("demo", Grid(1, 1))
        >>> session = Session(encounter)
        >>> session.encounter_orchestrator = orchestrator
        >>> session.encounter_state = Mock(
        ...     encounter_id="demo", requires_automatic_advance=Mock(return_value=True))
        >>> session.read = Mock(return_value=SessionRead(
        ...     "demo", (), None, None, (), {}, {}, {}, False
        ... ))
        >>> session.advance_until_input_required().messages
        (('Goblin', 'Waits'),)
        """
        return game_update(self, self._advance_automatic(single_action=False))

    def advance_one_automatic_action(self) -> GameUpdate:
        """Resolve one scripted action without introducing a time delay.

        Presentation clients can call this operation from their own timer while
        simulations use :meth:`advance_until_input_required` to run immediately.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.encounters.encounter_models.resolution import EncounterProgress
        >>> from srd_arena.domain.geometry import Grid
        >>> orchestrator = Mock()
        >>> orchestrator.advance_one_action.return_value = EncounterProgress(messages=[("Goblin", "Moves")])
        >>> encounter = EncounterDefinition("demo", Grid(1, 1))
        >>> session = Session(encounter)
        >>> session.encounter_orchestrator = orchestrator
        >>> session.encounter_state = Mock(
        ...     encounter_id="demo", requires_automatic_advance=Mock(return_value=True))
        >>> session.read = Mock(return_value=SessionRead(
        ...     "demo", (), None, None, (), {}, {}, {}, False
        ... ))
        >>> session.advance_one_automatic_action().messages
        (('Goblin', 'Moves'),)
        """
        return game_update(self, self._advance_automatic(single_action=True))

    def _advance_automatic(self, *, single_action: bool) -> EngineOutcome:
        """Resolve scripted activity with the requested execution granularity."""

        self._ensure_encounter_state()
        if self.encounter_state is None:
            raise RuntimeError("AI advancement requested without an active encounter.")
        if not self.encounter_state.requires_automatic_advance():
            raise RuntimeError(
                "AI advancement requested while no AI creature is active."
            )

        advance = (
            self.encounter_orchestrator.advance_one_action
            if single_action
            else self.encounter_orchestrator.advance
        )
        progress = advance(self.encounter_state)
        if progress.completed:
            self._complete_encounter()
            if self.pending_encounter_completion is not None:
                progress.messages = [
                    *progress.messages,
                    ("system", self.pending_encounter_completion.message),
                ]

        return EngineOutcome(
            messages=tuple(progress.messages),
            events=tuple(progress.events),
        )

    def _ensure_encounter_state(self) -> None:
        encounter = self.encounter
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
        self._encounter_actions = []

    def _restart_encounter(self) -> EngineOutcome:
        pending = self.pending_encounter_completion
        if pending is None:
            raise RuntimeError("Restart requested without a completed encounter.")
        self._restore_initial_state()
        self._ensure_encounter_state()
        return EngineOutcome(
            selected_choice_text=RESTART_CHOICE_TEXT,
            selected_action_id="system-restart-encounter",
        )

    def _restore_initial_state(self) -> None:
        self.creature_templates = deepcopy(self._initial_creature_templates)
        self.pending_encounter_completion = None
        self.encounter_state = None
        self._encounter_actions = []
        self._dice = self._dice.restarted()

    def _complete_encounter(self) -> None:
        self.pending_encounter_completion = PendingEncounterCompletion(
            message="Encounter complete"
        )
        self._encounter_actions = []


type SessionFactory = Callable[[EncounterDefinition], Session]
