"""In-process game interface for non-graphical clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from srd_arena.content.encounters import EncounterCatalog
from srd_arena.engine.api import (
    ActionObservation,
    CommandFailure,
    CommandResult,
    EncounterTerminationReason,
    GameCommand,
    GameObservation,
    GameplayObservation,
    GameUpdate,
    PlayerCommandResult,
    PlayerGameUpdate,
    PlayerObservation,
    SelectAction,
    Session,
)


class EpisodeState(StrEnum):
    """Lifecycle state of one headless encounter episode."""

    ACTIVE = "active"
    TERMINATED = "terminated"
    TRUNCATED = "truncated"


class EpisodeTruncationReason(StrEnum):
    """Non-rules reason a headless episode stopped before combat ended."""

    STEP_LIMIT = "step_limit"
    TURN_LIMIT = "turn_limit"


@dataclass(frozen=True)
class EpisodeStatus:
    """Report whether an episode is active, terminated, or truncated.

    Rules determine termination and its winner. The environment imposing a
    training limit determines truncation, which never invents a combat winner.

    >>> EpisodeStatus(EpisodeState.ACTIVE).terminated
    False
    >>> EpisodeStatus(
    ...     EpisodeState.TRUNCATED,
    ...     truncation_reason=EpisodeTruncationReason.STEP_LIMIT,
    ... ).truncated
    True
    """

    state: EpisodeState
    termination_reason: EncounterTerminationReason | None = None
    truncation_reason: EpisodeTruncationReason | None = None
    winning_team_id: str | None = None

    def __post_init__(self) -> None:
        if self.state is EpisodeState.ACTIVE and any(
            value is not None
            for value in (
                self.termination_reason,
                self.truncation_reason,
                self.winning_team_id,
            )
        ):
            raise ValueError("An active episode cannot have an outcome.")
        if self.state is EpisodeState.TERMINATED and (
            self.termination_reason is None or self.truncation_reason is not None
        ):
            raise ValueError("A terminated episode requires only a termination reason.")
        if self.state is EpisodeState.TRUNCATED and (
            self.truncation_reason is None
            or self.termination_reason is not None
            or self.winning_team_id is not None
        ):
            raise ValueError("A truncated episode requires only a truncation reason.")

    @property
    def terminated(self) -> bool:
        """Return whether combat rules ended the encounter."""

        return self.state is EpisodeState.TERMINATED

    @property
    def truncated(self) -> bool:
        """Return whether an environment limit stopped the episode."""

        return self.state is EpisodeState.TRUNCATED


@dataclass(frozen=True)
class NumericActionSlot:
    """Bind one decision-local numeric index to a semantic engine action."""

    index: int
    action_id: str
    label: str
    kind: str
    required_configuration: Literal["aim"] | None = None


@dataclass(frozen=True)
class DecisionActionMap:
    """Describe the deterministic numerical choices for one engine decision.

    Indices are stable for the lifetime of the decision ID. Consumers submit
    that identifier with a numerical choice so an index observed for an earlier
    decision cannot accidentally select an action in a later one.
    """

    decision_id: str
    slots: tuple[NumericActionSlot, ...]
    legal_action_mask: tuple[bool, ...]

    def __post_init__(self) -> None:
        """Reject maps whose slots and mask cannot be interpreted in parallel."""

        if len(self.slots) != len(self.legal_action_mask):
            raise ValueError("Action slots and the legal-action mask must align.")
        if any(slot.index != index for index, slot in enumerate(self.slots)):
            raise ValueError("Action-slot indices must be contiguous and ordered.")

    @property
    def legal_indices(self) -> tuple[int, ...]:
        """Return the numeric indices currently accepted by the adapter.

        >>> action_map = DecisionActionMap(
        ...     decision_id="turn:1",
        ...     slots=(
        ...         NumericActionSlot(0, "wait", "Wait", "action"),
        ...         NumericActionSlot(1, "attack", "Attack", "action"),
        ...     ),
        ...     legal_action_mask=(False, True),
        ... )
        >>> action_map.legal_indices
        (1,)
        """

        return tuple(
            index for index, legal in enumerate(self.legal_action_mask) if legal
        )


@dataclass(frozen=True)
class EncounterOption:
    """An encounter exposed to a headless controller by stable ID."""

    id: str
    label: str


@dataclass
class HeadlessGameAdapter:
    """Drive one game without depending on an interactive frontend.

    The adapter deliberately provides observations and legal options without
    choosing among them. A scripted controller or ML policy owns that choice.
    """

    catalog: EncounterCatalog
    _session: Session | None = field(default=None, init=False, repr=False)
    _episode_sequence: int = field(default=0, init=False, repr=False)
    _truncation_reason: EpisodeTruncationReason | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def available_encounters(self) -> tuple[EncounterOption, ...]:
        """Return selectable encounters without exposing filesystem paths.

        >>> from unittest.mock import Mock
        >>> catalog = Mock()
        >>> catalog.available_encounters.return_value = (Mock(id="demo", label="Demo"),)
        >>> HeadlessGameAdapter(catalog).available_encounters()
        (EncounterOption(id='demo', label='Demo'),)
        """

        return tuple(
            EncounterOption(id=encounter.id, label=encounter.label)
            for encounter in self.catalog.available_encounters()
        )

    def start_encounter(
        self,
        encounter_id: str,
        *,
        seed: int | None = None,
    ) -> GameObservation:
        """Start an encounter selected by its advertised stable ID.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.api import SceneObservation
        >>> observation = GameObservation(SceneObservation("intro", ()), None, None, False)
        >>> catalog, session = Mock(), Mock()
        >>> catalog.available_encounters.return_value = (Mock(id="demo", label="Demo"),)
        >>> catalog.load_encounter.return_value = Mock()
        >>> session = Mock()
        >>> session.observe.return_value = observation
        >>> from unittest.mock import patch
        >>> with patch("srd_arena.frontends.headless.adapter.Session", return_value=session):
        ...     result = HeadlessGameAdapter(catalog).start_encounter("demo")
        >>> result.scene.scene_id
        'intro'
        """

        summary = next(
            (
                encounter
                for encounter in self.catalog.available_encounters()
                if encounter.id == encounter_id
            ),
            None,
        )
        if summary is None:
            raise KeyError(f"Unknown encounter '{encounter_id}'.")
        self._episode_sequence += 1
        session = Session(
            self.catalog.load_encounter(summary.id),
            seed=seed,
            decision_epoch=self._episode_sequence,
        )
        observation = session.observe()
        self._session = session
        self._truncation_reason = None
        return observation

    def observe(self) -> GameObservation:
        """Return the current structured game observation.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.api import SceneObservation
        >>> observation = GameObservation(SceneObservation("intro", ()), None, None, False)
        >>> session = Mock()
        >>> session.observe.return_value = observation
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.observe().scene.scene_id
        'intro'
        """

        return self._require_session().observe()

    def observe_gameplay(self) -> GameplayObservation:
        """Return unrestricted gameplay facts and the complete recorded history.

        >>> adapter = HeadlessGameAdapter(EncounterCatalog())
        >>> _ = adapter.start_encounter("warlock_training", seed=42)
        >>> adapter.observe_gameplay().history
        ()
        """

        return self._require_session().observe_gameplay()

    def observe_player(self, perspective_team_id: str) -> PlayerObservation:
        """Return the framework-neutral partial observation for one allied team."""

        return self._require_session().observe_player(perspective_team_id)

    def start_player_encounter(
        self,
        encounter_id: str,
        perspective_team_id: str,
        *,
        seed: int | None = None,
    ) -> PlayerObservation:
        """Start an encounter and return only the requested team's observation."""

        self.start_encounter(encounter_id, seed=seed)
        return self.observe_player(perspective_team_id)

    def available_actions(self) -> tuple[ActionObservation, ...]:
        """Return implemented, eligible actions at the current decision point.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.api import SceneObservation
        >>> actions = (
        ...     ActionObservation("dodge", "Dodge", "action", "hero"),
        ...     ActionObservation(
        ...         "dash", "Dash", "action", "hero", availability="unavailable"
        ...     ),
        ...     ActionObservation(
        ...         "help", "Help", "action", "hero", enabled=False
        ...     ),
        ... )
        >>> observation = GameObservation(
        ...     SceneObservation("fight", actions), None, None, False
        ... )
        >>> session = Mock()
        >>> session.observe.return_value = observation
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> tuple(action.id for action in adapter.available_actions())
        ('dodge',)
        """

        if self._truncation_reason is not None:
            return ()
        return tuple(
            action
            for action in self.observe().scene.action_details
            if action.enabled and action.availability == "available"
        )

    def available_action_ids(self) -> tuple[str, ...]:
        """Return stable IDs suitable for an action mask or model choice.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.api import SceneObservation
        >>> action = ActionObservation("dodge", "Dodge", "action", "hero")
        >>> observation = GameObservation(SceneObservation("fight", (action,)), None, None, False)
        >>> session = Mock()
        >>> session.observe.return_value = observation
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.available_action_ids()
        ('dodge',)
        """

        return tuple(action.id for action in self.available_actions())

    def decision_action_map(self) -> DecisionActionMap:
        """Return a deterministic numeric map and mask for the current decision.

        The map includes unavailable and unimplemented gameplay options so a
        controller can distinguish an illegal choice from an absent one. System
        controls such as restart and exit are deliberately not policy actions.
        """

        observation = self.observe()
        if observation.encounter is None:
            raise RuntimeError("No encounter decision is currently available.")
        return _decision_action_map(
            decision_id=observation.encounter.decision.id,
            actions=observation.scene.action_details,
            accepts_actions=(
                observation.completion is None and self._truncation_reason is None
            ),
        )

    def player_decision_action_map(
        self,
        perspective_team_id: str,
    ) -> DecisionActionMap:
        """Return a deterministic action map derived only from player-known facts."""

        observation = self.observe_player(perspective_team_id)
        return _decision_action_map(
            decision_id=observation.decision.id,
            actions=observation.action_details,
            accepts_actions=(
                observation.completion is None and self._truncation_reason is None
            ),
        )

    def select_action_index(
        self,
        action_index: int,
        *,
        expected_decision_id: str,
    ) -> CommandResult:
        """Submit a legal numerical choice from an observed decision map."""

        if self._truncation_reason is not None:
            return CommandResult(
                failure=CommandFailure(
                    code="episode_truncated",
                    message="Reset the episode before submitting another command.",
                )
            )
        action_map = self.decision_action_map()
        if action_map.decision_id != expected_decision_id:
            return CommandResult(
                failure=CommandFailure(
                    code="stale_decision",
                    message=(
                        f"Decision '{expected_decision_id}' is stale; "
                        f"the current decision is '{action_map.decision_id}'."
                    ),
                )
            )
        if not 0 <= action_index < len(action_map.slots):
            return CommandResult(
                failure=CommandFailure(
                    code="invalid_action_index",
                    message=f"Action index {action_index} is outside the current map.",
                )
            )
        if not action_map.legal_action_mask[action_index]:
            return CommandResult(
                failure=CommandFailure(
                    code="action_unavailable",
                    message=f"Action index {action_index} is not currently legal.",
                )
            )
        return self.select_action(
            action_map.slots[action_index].action_id,
            expected_decision_id=expected_decision_id,
        )

    def select_player_action_index(
        self,
        perspective_team_id: str,
        action_index: int,
        *,
        expected_decision_id: str,
    ) -> PlayerCommandResult:
        """Submit one legal index from a player-relative decision map."""

        if self._truncation_reason is not None:
            return PlayerCommandResult(
                failure=CommandFailure(
                    code="episode_truncated",
                    message="Reset the episode before submitting another command.",
                )
            )
        action_map = self.player_decision_action_map(perspective_team_id)
        if action_map.decision_id != expected_decision_id:
            return PlayerCommandResult(
                failure=CommandFailure(
                    code="stale_decision",
                    message=(
                        f"Decision '{expected_decision_id}' is stale; "
                        f"the current decision is '{action_map.decision_id}'."
                    ),
                )
            )
        if not 0 <= action_index < len(action_map.slots):
            return PlayerCommandResult(
                failure=CommandFailure(
                    code="invalid_action_index",
                    message=f"Action index {action_index} is outside the current map.",
                )
            )
        if not action_map.legal_action_mask[action_index]:
            return PlayerCommandResult(
                failure=CommandFailure(
                    code="action_unavailable",
                    message=f"Action index {action_index} is not currently legal.",
                )
            )
        return self.select_player_action(
            perspective_team_id,
            action_map.slots[action_index].action_id,
            expected_decision_id=expected_decision_id,
        )

    def select_action(
        self,
        action_id: str,
        *,
        expected_decision_id: str | None,
    ) -> CommandResult:
        """Submit one advertised action against the observed decision.

        >>> from unittest.mock import Mock
        >>> session = Mock()
        >>> session.execute.return_value = CommandResult(update=Mock())
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.select_action("dodge", expected_decision_id="turn:1").accepted
        True
        >>> command = session.execute.call_args.args[0]
        >>> (command.action_id, command.expected_decision_id)
        ('dodge', 'turn:1')
        """

        return self.submit(
            SelectAction(
                action_id=action_id,
                expected_decision_id=expected_decision_id,
            )
        )

    def select_player_action(
        self,
        perspective_team_id: str,
        action_id: str,
        *,
        expected_decision_id: str,
    ) -> PlayerCommandResult:
        """Submit one action through the player-relative command boundary."""

        return self.submit_player(
            perspective_team_id,
            SelectAction(
                action_id=action_id,
                expected_decision_id=expected_decision_id,
            ),
        )

    def submit(self, command: GameCommand) -> CommandResult:
        """Submit any engine command, including staged targeting.

        >>> from unittest.mock import Mock
        >>> session = Mock()
        >>> expected = CommandResult(failure=CommandFailure("example", "Example"))
        >>> session.execute.return_value = expected
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.submit(SelectAction("dodge", "turn:1")) is expected
        True
        """

        if self._truncation_reason is not None:
            return CommandResult(
                failure=CommandFailure(
                    code="episode_truncated",
                    message="Reset the episode before submitting another command.",
                )
            )
        return self._require_session().execute(command)

    def submit_player(
        self,
        perspective_team_id: str,
        command: GameCommand,
    ) -> PlayerCommandResult:
        """Submit a command and return only a player-relative update."""

        if self._truncation_reason is not None:
            return PlayerCommandResult(
                failure=CommandFailure(
                    code="episode_truncated",
                    message="Reset the episode before submitting another command.",
                )
            )
        return self._require_session().execute_player(
            perspective_team_id,
            command,
        )

    def advance_until_input_required(self) -> GameUpdate:
        """Advance scripted controllers until external input is required.

        >>> from unittest.mock import Mock
        >>> session = Mock()
        >>> update = Mock()
        >>> session.advance_until_input_required.return_value = update
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.advance_until_input_required() is update
        True
        """

        self._require_active_episode()
        return self._require_session().advance_until_input_required()

    def advance_player_until_input_required(
        self,
        perspective_team_id: str,
    ) -> PlayerGameUpdate:
        """Advance scripted controllers without returning privileged state."""

        self._require_active_episode()
        return self._require_session().advance_player_until_input_required(
            perspective_team_id
        )

    def advance_one_automatic_action(self) -> GameUpdate:
        """Resolve one scripted action for step-oriented clients.

        >>> from unittest.mock import Mock
        >>> session = Mock()
        >>> update = Mock()
        >>> session.advance_one_automatic_action.return_value = update
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.advance_one_automatic_action() is update
        True
        """

        self._require_active_episode()
        return self._require_session().advance_one_automatic_action()

    def advance_one_player_automatic_action(
        self,
        perspective_team_id: str,
    ) -> PlayerGameUpdate:
        """Resolve one scripted action through the player-safe boundary."""

        self._require_active_episode()
        return self._require_session().advance_one_player_automatic_action(
            perspective_team_id
        )

    @property
    def seed(self) -> int | None:
        """Return the seed governing the active encounter, if any."""

        return self._require_session().seed

    def reset(self, *, seed: int | None = None) -> GameObservation:
        """Reset the active game to its initial observation.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.api import SceneObservation
        >>> initial = GameObservation(
        ...     SceneObservation("intro", ()), None, None, False
        ... )
        >>> session = Mock()
        >>> session.reset.return_value = initial
        >>> adapter = HeadlessGameAdapter(Mock())
        >>> adapter._session = session
        >>> adapter.reset().scene.scene_id
        'intro'
        """

        observation = self._require_session().reset(seed=seed)
        self._truncation_reason = None
        return observation

    def episode_status(self) -> EpisodeStatus:
        """Return a typed episode outcome without interpreting display text."""

        completion = self.observe().completion
        if completion is not None:
            return EpisodeStatus(
                state=EpisodeState.TERMINATED,
                termination_reason=completion.reason,
                winning_team_id=completion.winning_team_id,
            )
        if self._truncation_reason is not None:
            return EpisodeStatus(
                state=EpisodeState.TRUNCATED,
                truncation_reason=self._truncation_reason,
            )
        return EpisodeStatus(state=EpisodeState.ACTIVE)

    def truncate(self, reason: EpisodeTruncationReason) -> EpisodeStatus:
        """Stop an active episode for an environment-imposed limit.

        Truncation is deliberately explicit: the combat engine never guesses a
        training horizon or treats it as a rules-driven victory.
        """

        status = self.episode_status()
        if status.terminated:
            raise RuntimeError("A terminated encounter cannot be truncated.")
        if status.truncated:
            raise RuntimeError("A truncated encounter must be reset before reuse.")
        self._truncation_reason = reason
        return self.episode_status()

    def _require_active_episode(self) -> None:
        if self._truncation_reason is not None:
            raise RuntimeError("Reset the truncated episode before advancing it.")

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Start an encounter before interacting with the game.")
        return self._session


def _decision_action_map(
    *,
    decision_id: str,
    actions: tuple[ActionObservation, ...],
    accepts_actions: bool,
) -> DecisionActionMap:
    """Build the shared deterministic index mapping for one observation."""

    ordered_actions = tuple(
        sorted(
            (action for action in actions if not action.kind.startswith("system_")),
            key=lambda action: action.id,
        )
    )
    slots = tuple(
        NumericActionSlot(
            index=index,
            action_id=action.id,
            label=action.label,
            kind=action.kind,
            required_configuration=action.required_configuration,
        )
        for index, action in enumerate(ordered_actions)
    )
    legal_action_mask = tuple(
        accepts_actions
        and action.enabled
        and action.availability == "available"
        and action.required_configuration is None
        for action in ordered_actions
    )
    return DecisionActionMap(
        decision_id=decision_id,
        slots=slots,
        legal_action_mask=legal_action_mask,
    )
