"""Application facade for one running game."""

from __future__ import annotations

from srd_arena.engine.session import Session

from .commands import CommandResult, GameCommand, GameUpdate
from .interactions import execute_game_command, game_update
from .observations import GameObservation, observe_session


class RunningGame:
    """Application facade around one private evolving game session."""

    __slots__ = ("__session",)

    def __init__(self, session: Session) -> None:
        self.__session = session

    def observe(self) -> GameObservation:
        """Return a read-only snapshot of the current decision point."""

        return observe_session(self.__session)

    def advance_automatic(self) -> GameUpdate:
        """Advance scripted controllers until the engine yields control."""

        return game_update(
            self.__session,
            self.__session.advance_until_input_required(),
        )

    def execute(self, command: GameCommand) -> CommandResult:
        """Validate and execute one explicit interaction command."""

        return execute_game_command(self.__session, command)

    def reset(self) -> GameObservation:
        """Start a fresh episode of the same game.

        This supports clients that repeatedly run the same scenario, such as
        headless simulations, without reloading its authored content.
        """

        self.__session.reset()
        return self.observe()
