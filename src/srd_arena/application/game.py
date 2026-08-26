"""Application facade for one running game."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from srd_arena.domain.equipment import Item
from srd_arena.runtime.models import TurnResult
from srd_arena.runtime.session import Session

from .observations import GameObservation, observe_session


@dataclass(frozen=True)
class RunningGame:
    """Application facade around one private evolving game session.

    The public session field remains temporarily available to the Qt adapter.
    Observation and command slices will remove that final runtime exposure once
    Qt has equivalent application contracts.
    """

    scenario_directory: Path
    items: tuple[Item, ...]
    session: Session

    def observe(self) -> GameObservation:
        """Return a read-only snapshot of the current decision point."""

        return observe_session(self.session)

    def select_action(self, action_id: str) -> TurnResult:
        """Select an action advertised by the current observation."""

        return self.session.choose(action_id)

    def advance_automatic(self) -> TurnResult:
        """Advance scripted controllers until the engine yields control."""

        return self.session.advance_until_input_required()

    def reset(self) -> GameObservation:
        """Reset the running game and return its initial observation."""

        self.session.reset()
        return self.observe()
