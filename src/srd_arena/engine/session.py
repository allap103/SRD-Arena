"""Own mutable game state and expose the frontend-neutral engine API."""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass

from srd_arena.domain.encounters import EncounterDefinition, EncounterOrchestrator
from srd_arena.domain.encounters.actions.option_discovery.spell_selection import (
    spell_target_selection_actions,
)
from srd_arena.domain.encounters.actions.options import decision_actions
from srd_arena.domain.encounters.creature_control import creature_action_candidates
from srd_arena.domain.encounters.encounter import EncounterState
from srd_arena.domain.encounters.encounter_models.actions import EncounterAction
from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent
from srd_arena.domain.encounters.event_visibility import event_visibility
from srd_arena.domain.encounters.turn_lifecycle import surviving_team_ids
from srd_arena.domain.rolls.randomness import DiceRoller
from srd_arena.engine.action_configuration import (
    configure_action as configure_engine_action,
)
from srd_arena.engine.commands import (
    CommandResult,
    GameCommand,
    GameUpdate,
    PlayerCommandResult,
    PlayerGameUpdate,
)
from srd_arena.engine.gameplay_observation_models import (
    GameplayEventObservation,
    GameplayObservation,
)
from srd_arena.engine.gameplay_observations import capture_gameplay
from srd_arena.engine.interactions import execute_game_command, game_update
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.observations import (
    EncounterTerminationReason,
    GameObservation,
    observe_session,
)
from srd_arena.engine.player_interactions import (
    execute_player_game_command,
    player_game_update,
)
from srd_arena.engine.player_knowledge import TeamKnowledge
from srd_arena.engine.player_observation_models import PlayerObservation
from srd_arena.engine.player_observations import observe_player_session
from srd_arena.engine.queries import (
    EXIT_CHOICE_TEXT,
    RESTART_CHOICE_TEXT,
    ActionConfiguration,
    SessionRead,
)
from srd_arena.engine.session_queries import read_session
from srd_arena.engine.values import freeze_mapping


@dataclass
class PendingEncounterCompletion:
    """Hold a completed encounter until the client chooses what to do next."""

    message: str
    reason: EncounterTerminationReason = EncounterTerminationReason.LAST_TEAM_STANDING
    winning_team_id: str | None = None


class Session:
    """Coordinate a loaded encounter and its mutable state for one running game.

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
        *,
        seed: int | None = None,
        decision_epoch: int = 0,
    ):
        if dice is not None and seed is not None:
            raise ValueError("Provide either dice or seed, not both.")
        self.encounter = encounter
        self.creature_templates = {
            creature.id: creature for creature in encounter.creatures
        }
        self.item_templates = {item.id: item for item in encounter.items}
        self._initial_creature_templates = deepcopy(self.creature_templates)
        self.geometry_config = encounter.geometry_config
        self.encounter_orchestrator = EncounterOrchestrator()
        self._dice = dice or (
            DiceRoller.seeded(seed) if seed is not None else DiceRoller()
        )
        self.encounter_state: EncounterState | None = None
        self._encounter_actions: list[EncounterAction] = []
        self.pending_encounter_completion: PendingEncounterCompletion | None = None
        self._decision_epoch = decision_epoch
        self._decision_revision = 0
        self._player_knowledge: dict[str, TeamKnowledge] = {}
        self._gameplay_history: list[GameplayEventObservation] = []
        self._history_episode = 0

    def _read(self) -> SessionRead:
        """Return typed internal inputs used to construct an observation.

        >>> from srd_arena.domain.geometry import Grid
        >>> encounter = EncounterDefinition("demo", Grid(1, 1))
        >>> session = Session(encounter)
        >>> session.pending_encounter_completion = PendingEncounterCompletion(
        ...     "Encounter complete"
        ... )
        >>> session._read().completion_message
        'Encounter complete'
        """

        return read_session(self)

    def observe(self) -> GameObservation:
        """Return an immutable snapshot of the current decision point.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.queries import SessionRead
        >>> from srd_arena.domain.geometry import Grid
        >>> session = Session(EncounterDefinition("demo", Grid(1, 1)))
        >>> session._read = Mock(return_value=SessionRead(
        ...     "demo", (), None, None, (), {}, {}, {}, False
        ... ))
        >>> session.observe().scene.scene_id
        'demo'
        """

        return observe_session(self)

    def observe_gameplay(self) -> GameplayObservation:
        """Return unrestricted gameplay facts and the full recorded episode history.

        >>> from srd_arena.content.encounters import EncounterCatalog
        >>> session = Session(EncounterCatalog().load_encounter("warlock_training"), seed=42)
        >>> snapshot = session.observe_gameplay()
        >>> snapshot.schema_id
        'gameplay-observation-v1-draft'
        >>> snapshot.history
        ()
        """

        return capture_gameplay(
            self._read(),
            history=tuple(self._gameplay_history),
            episode_id=(self._decision_epoch, self._history_episode),
        )

    def observe_player(self, perspective_team_id: str) -> PlayerObservation:
        """Return one allied team's partial, shared-knowledge observation."""

        knowledge = self._player_knowledge.setdefault(
            perspective_team_id,
            TeamKnowledge(perspective_team_id),
        )
        return observe_player_session(self, perspective_team_id, knowledge)

    def execute(self, command: GameCommand) -> CommandResult:
        """Validate and execute one frontend-neutral interaction command.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.commands import SelectAction
        >>> from srd_arena.engine.queries import SessionRead
        >>> from srd_arena.domain.geometry import Grid
        >>> session = Session(EncounterDefinition("demo", Grid(1, 1)))
        >>> session._read = Mock(return_value=SessionRead(
        ...     "demo", (), None, None, (), {}, {}, {}, False
        ... ))
        >>> session.execute(SelectAction("wait", "old")).failure.code
        'stale_decision'
        """

        return execute_game_command(self, command)

    def execute_player(
        self,
        perspective_team_id: str,
        command: GameCommand,
    ) -> PlayerCommandResult:
        """Execute a command through the non-privileged player boundary."""

        return execute_player_game_command(self, perspective_team_id, command)

    def _choose(self, action_id: str) -> EngineOutcome:
        """Execute one action advertised by the current engine read.

        System exit remains available at an encounter decision point.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> encounter = EncounterDefinition("demo", Grid(1, 1))
        >>> session = Session(encounter)
        >>> session.encounter_state = Mock(encounter_id="demo")
        >>> outcome = session._choose("system-exit")
        >>> (outcome.selected_action_id, outcome.should_exit)
        ('system-exit', True)
        """
        if self.pending_encounter_completion is not None:
            if action_id == "system-restart-encounter":
                outcome = self._restart_encounter()
            elif action_id == "system-exit":
                outcome = self._exit_game()
            else:
                raise KeyError(
                    f"Action '{action_id}' is unavailable for the completion prompt."
                )
        else:
            self._ensure_encounter_state()
            if action_id == "system-exit":
                outcome = self._exit_game()
            elif self.encounter_state is not None:
                outcome = self._choose_encounter(action_id)
            else:
                raise RuntimeError("No encounter is active.")
        self._decision_revision += 1
        return outcome

    def _choose_player_action(self, action_id: str) -> EngineOutcome:
        """Attempt one action advertised by a player-relative observation.

        Player observations may intentionally expose an attempt whose private
        target requirement fails. Such candidates still enter the ordinary
        domain execution pipeline, which reports the failure without spending
        the action's resources.
        """

        self._ensure_encounter_state()
        state = self.encounter_state
        if state is None:
            raise RuntimeError("No encounter is active.")
        action = next(
            (
                candidate
                for candidate in self._player_action_candidates()
                if candidate.id == action_id
            ),
            None,
        )
        if action is None:
            raise KeyError(f"Action '{action_id}' is unavailable.")
        outcome = self._apply_encounter_action(
            action,
            selected_choice_text=action.label,
        )
        self._decision_revision += 1
        return outcome

    def _player_action_candidates(self) -> tuple[EncounterAction, ...]:
        """Return current candidates including privately ineligible targets."""

        state = self.encounter_state
        if state is None:
            return ()
        decision = state.current_decision()
        if decision.kind == "turn":
            return tuple(creature_action_candidates(state, decision.creature_ref))
        if decision.kind == "spell_targets":
            return tuple(
                spell_target_selection_actions(
                    state,
                    decision.creature_ref,
                    include_unavailable=True,
                )
            )
        return tuple(decision_actions(state))

    @property
    def seed(self) -> int | None:
        """Return the seed governing this session's random stream, if any."""

        return self._dice.seed

    @property
    def decision_revision(self) -> int:
        """Return the monotonic revision of the public decision surface."""

        return self._decision_revision

    @property
    def decision_epoch(self) -> int:
        """Return the namespace separating this session from prior episodes."""

        return self._decision_epoch

    def reset(self, *, seed: int | None = None) -> GameObservation:
        """Restore the session to its initially loaded content and scene.

        A seeded session also rewinds its private dice stream, so repeating the
        same decisions after reset produces the same random outcomes. Supplying
        a new seed starts and owns that reproducible stream instead.

        >>> from srd_arena.domain.geometry import Grid
        >>> encounter = EncounterDefinition("demo", Grid(1, 1))
        >>> session = Session(encounter)
        >>> from unittest.mock import Mock
        >>> session.observe = Mock(return_value=None)
        >>> session.reset()
        >>> session.encounter_state is None
        True
        """
        self._restore_initial_state(seed=seed)
        self._decision_revision += 1
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
        if not action.aim_committed:
            raise ValueError(f"Action '{action_id}' requires aim configuration.")
        return self._apply_encounter_action(
            action,
            selected_choice_text=action.label,
        )

    def _configure_action(
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
        >>> session._configure_action("missing", ActionAim(1, 1))
        Traceback (most recent call last):
        ...
        KeyError: "Action 'missing' is unavailable."
        """

        outcome = configure_engine_action(self, action_id, configuration)
        self._decision_revision += 1
        return outcome

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

        outcome = EngineOutcome(
            selected_choice_text=selected_choice_text,
            selected_action_id=action.id,
            messages=tuple(messages),
            events=tuple(progress.events),
        )
        self._record_gameplay_events(outcome.events)
        return outcome

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
        >>> session._read = Mock(return_value=SessionRead(
        ...     "demo", (), None, None, (), {}, {}, {}, False
        ... ))
        >>> session.advance_until_input_required().messages
        (('Goblin', 'Waits'),)
        """
        return game_update(self, self._advance_automatic(single_action=False))

    def advance_player_until_input_required(
        self,
        perspective_team_id: str,
    ) -> PlayerGameUpdate:
        """Advance scripted turns and return only player-relative state."""

        return player_game_update(
            self,
            perspective_team_id,
            self._advance_automatic(single_action=False),
        )

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
        >>> session._read = Mock(return_value=SessionRead(
        ...     "demo", (), None, None, (), {}, {}, {}, False
        ... ))
        >>> session.advance_one_automatic_action().messages
        (('Goblin', 'Moves'),)
        """
        return game_update(self, self._advance_automatic(single_action=True))

    def advance_one_player_automatic_action(
        self,
        perspective_team_id: str,
    ) -> PlayerGameUpdate:
        """Resolve one scripted action and return only player-relative state."""

        return player_game_update(
            self,
            perspective_team_id,
            self._advance_automatic(single_action=True),
        )

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

        self._decision_revision += 1
        outcome = EngineOutcome(
            messages=tuple(progress.messages),
            events=tuple(progress.events),
        )
        self._record_gameplay_events(outcome.events)
        return outcome

    def _record_gameplay_events(
        self,
        events: tuple[CombatEvent, ...],
    ) -> None:
        """Retain detached events before updating team knowledge from the journal."""

        if self.encounter_state is None or not events:
            return
        # Normal events carry their own emission-time snapshot. Synthetic events
        # supplied directly by callers use current sight, never the last UI read.
        visibility = dict(event_visibility(self.encounter_state))
        self._gameplay_history.extend(
            GameplayEventObservation(
                seq=event.seq,
                type=event.type,
                creature_ref=event.creature_ref,
                frame_id=event.frame_id,
                action_id=event.action_id,
                data=freeze_mapping(event.data),
                visible_by_team=(
                    event.visible_by_team
                    if event.visible_by_team is not None
                    else tuple(visibility.items())
                ),
            )
            for event in events
        )
        for team_id in visibility:
            knowledge = self._player_knowledge.setdefault(
                team_id, TeamKnowledge(team_id)
            )
            knowledge.record_history(
                (self._decision_epoch, self._history_episode),
                tuple(self._gameplay_history),
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
        self.encounter_state.capture_event_visibility = True
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

    def _restore_initial_state(self, *, seed: int | None = None) -> None:
        self.creature_templates = deepcopy(self._initial_creature_templates)
        self.pending_encounter_completion = None
        self.encounter_state = None
        self._encounter_actions = []
        self._player_knowledge.clear()
        self._gameplay_history.clear()
        self._history_episode += 1
        self._dice = (
            DiceRoller.seeded(seed) if seed is not None else self._dice.restarted()
        )

    def _complete_encounter(self) -> None:
        if self.encounter_state is None:
            raise RuntimeError("Cannot complete an encounter before it has started.")
        surviving_teams = surviving_team_ids(self.encounter_state)
        self.pending_encounter_completion = PendingEncounterCompletion(
            message="Encounter complete",
            reason=(
                EncounterTerminationReason.LAST_TEAM_STANDING
                if surviving_teams
                else EncounterTerminationReason.ALL_TEAMS_DEFEATED
            ),
            winning_team_id=(surviving_teams[0] if surviving_teams else None),
        )
        self._encounter_actions = []


type SessionFactory = Callable[[EncounterDefinition], Session]
