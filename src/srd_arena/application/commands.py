"""Frontend-neutral commands and results for one running game."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from .observations import GameObservation


@dataclass(frozen=True)
class SelectAction:
    action_id: str
    expected_decision_id: str | None


@dataclass(frozen=True)
class AimAction:
    action_id: str
    x: float
    y: float
    expected_decision_id: str


@dataclass(frozen=True)
class ChangeTarget:
    target_ref: str
    remove: bool
    expected_decision_id: str
    source_trigger_id: str | None = None


@dataclass(frozen=True)
class SetResourceAllocation:
    target_ref: str
    amount: int
    expected_decision_id: str


@dataclass(frozen=True)
class ConfirmTargeting:
    expected_decision_id: str


@dataclass(frozen=True)
class CancelTargeting:
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
    """Application-owned record of an event emitted while resolving a command."""

    seq: int
    type: str
    creature_ref: str | None = None
    frame_id: str | None = None
    action_id: str | None = None
    data: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True)
class GameUpdate:
    """Application-owned result of one accepted game command."""

    observation: GameObservation
    messages: tuple[tuple[str, str], ...]
    events: tuple[GameEvent, ...]
    selected_action_id: str | None
    selected_choice_text: str | None
    scene_changed: bool
    should_exit: bool


@dataclass(frozen=True)
class CommandFailure:
    code: str
    message: str


@dataclass(frozen=True)
class CommandResult:
    update: GameUpdate | None = None
    failure: CommandFailure | None = None

    @property
    def accepted(self) -> bool:
        return self.update is not None
