"""Frontend-neutral commands and results for one engine session."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from .observations import GameObservation
from .values import EngineValue, freeze_mapping


@dataclass(frozen=True)
class SelectAction:
    """Choose one action advertised for the expected decision point."""

    action_id: str
    expected_decision_id: str | None


@dataclass(frozen=True)
class AimAction:
    """Choose an advertised area action and place its origin on the grid."""

    action_id: str
    x: float
    y: float
    expected_decision_id: str


@dataclass(frozen=True)
class ChangeTarget:
    """Add or remove a creature from an active staged target selection."""

    target_ref: str
    remove: bool
    expected_decision_id: str
    source_trigger_id: str | None = None


@dataclass(frozen=True)
class SetResourceAllocation:
    """Assign an amount from a shared action resource to one target."""

    target_ref: str
    amount: int
    expected_decision_id: str


@dataclass(frozen=True)
class ConfirmTargeting:
    """Confirm the targets and allocations staged for the current decision."""

    expected_decision_id: str


@dataclass(frozen=True)
class CancelTargeting:
    """Cancel the target selection staged for the current decision."""

    expected_decision_id: str


GameCommand = (
    SelectAction
    | AimAction
    | ChangeTarget
    | SetResourceAllocation
    | ConfirmTargeting
    | CancelTargeting
)


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
class CommandFailure:
    """Structured explanation for a command rejected by the engine."""

    code: str
    message: str


@dataclass(frozen=True)
class CommandResult:
    """Exactly one accepted update or rejected-command failure."""

    update: GameUpdate | None = None
    failure: CommandFailure | None = None

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
