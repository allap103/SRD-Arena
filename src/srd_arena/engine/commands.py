"""Frontend-neutral commands and results for one engine session."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from .observations import GameObservation
from .player_observation_models import PlayerObservation
from .values import EngineValue, freeze_mapping


@dataclass(frozen=True)
class SelectAction:
    """Choose one action advertised for the expected decision point."""

    action_id: str
    expected_decision_id: str | None


@dataclass(frozen=True)
class AimAction:
    """Choose a destination or origin for an advertised point-aimed action."""

    action_id: str
    x: float
    y: float
    expected_decision_id: str


@dataclass(frozen=True)
class CastSpell:
    """Submit one complete cast, with ordered targets, allocations and optional aim."""

    action_id: str
    expected_decision_id: str
    target_refs: tuple[str, ...] = ()
    allocations: tuple[tuple[str, int], ...] = ()
    aim: tuple[float, float] | None = None


GameCommand = SelectAction | AimAction | CastSpell


@dataclass(frozen=True)
class GameEvent:
    """Engine-owned record of an event emitted while resolving a command."""

    seq: int
    type: str
    creature_ref: str | None = None
    frame_id: str | None = None
    action_id: str | None = None
    data: Mapping[str, EngineValue] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", freeze_mapping(self.data))


@dataclass(frozen=True)
class GameUpdate:
    """Engine-owned result of one accepted game command."""

    observation: GameObservation
    messages: tuple[tuple[str, str], ...]
    events: tuple[GameEvent, ...]
    selected_action_id: str | None
    selected_choice_text: str | None
    should_exit: bool


@dataclass(frozen=True)
class PlayerGameUpdate:
    """Result of one accepted command without a privileged state snapshot."""

    observation: PlayerObservation
    messages: tuple[tuple[str, str], ...]
    events: tuple[GameEvent, ...]
    selected_action_id: str | None
    selected_choice_text: str | None
    should_exit: bool


@dataclass(frozen=True)
class CommandFailure:
    """Structured explanation for a command rejected by the engine."""

    code: str
    message: str


@dataclass(frozen=True)
class CommandResult:
    """Exactly one accepted update or rejected-command failure."""

    update: GameUpdate | None = None
    failure: CommandFailure | None = None

    def __post_init__(self) -> None:
        """Require exactly one accepted update or rejection failure."""

        if (self.update is None) == (self.failure is None):
            raise ValueError("A command result requires exactly one update or failure.")

    @property
    def accepted(self) -> bool:
        """Return whether the command produced an engine update.

        >>> from unittest.mock import Mock
        >>> CommandResult(update=Mock()).accepted
        True
        >>> CommandResult(failure=CommandFailure("stale", "Decision changed")).accepted
        False
        """
        return self.update is not None


@dataclass(frozen=True)
class PlayerCommandResult:
    """Exactly one player-safe update or rejected-command failure."""

    update: PlayerGameUpdate | None = None
    failure: CommandFailure | None = None

    def __post_init__(self) -> None:
        if (self.update is None) == (self.failure is None):
            raise ValueError("A command result requires exactly one update or failure.")

    @property
    def accepted(self) -> bool:
        """Return whether the player command produced an engine update."""

        return self.update is not None
