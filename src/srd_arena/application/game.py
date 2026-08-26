"""Application facade for one running game."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from srd_arena.domain.equipment import Item
from srd_arena.runtime.session import Session

from .commands import CommandResult, GameCommand, GameUpdate, SelectAction
from .interactions import decision_id, execute_game_command, game_update
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

    def select_action(self, action_id: str) -> GameUpdate:
        """Select an action advertised by the current observation."""

        result = self.execute(
            SelectAction(
                action_id=action_id,
                expected_decision_id=decision_id(self.observe()),
            )
        )
        if result.update is None:
            assert result.failure is not None
            raise RuntimeError(result.failure.message)
        return result.update

    def advance_automatic(self) -> GameUpdate:
        """Advance scripted controllers until the engine yields control."""

        return game_update(self.session, self.session.advance_until_input_required())

    def execute(self, command: GameCommand) -> CommandResult:
        """Validate and execute one explicit interaction command."""

        return execute_game_command(self.session, command)

    def reset(self) -> GameObservation:
        """Reset the running game and return its initial observation."""

        self.session.reset()
        return self.observe()
