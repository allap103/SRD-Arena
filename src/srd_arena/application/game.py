"""Application facade for one running game."""

from __future__ import annotations

from srd_arena.engine.api import GameEngine

from .commands import CommandResult, GameCommand, GameUpdate
from .interactions import execute_game_command, game_update
from .observations import GameObservation, observe_session


class RunningGame:
    """Application facade around one private evolving game session."""

    __slots__ = ("__session",)

    def __init__(self, session: GameEngine) -> None:
        self.__session = session

    def observe(self) -> GameObservation:
        """Return a read-only snapshot of the current decision point.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.queries import SessionRead
        >>> read = SessionRead("intro", "Welcome", (), None, None, (), {}, {}, {}, False)
        >>> engine = Mock()
        >>> engine.read.return_value = read
        >>> RunningGame(engine).observe().scene.scene_text
        'Welcome'
        """

        return observe_session(self.__session)

    def advance_until_input_required(self) -> GameUpdate:
        """Run scripted controllers immediately until the engine needs input.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.models import EngineOutcome
        >>> from srd_arena.engine.queries import SessionRead
        >>> engine = Mock()
        >>> engine.read.return_value = SessionRead("intro", None, (), None, None, (), {}, {}, {}, False)
        >>> engine.advance_until_input_required.return_value = EngineOutcome(messages=(("System", "Done"),))
        >>> RunningGame(engine).advance_until_input_required().messages
        (('System', 'Done'),)
        """

        return game_update(
            self.__session,
            self.__session.advance_until_input_required(),
        )

    def advance_one_automatic_action(self) -> GameUpdate:
        """Resolve one scripted action and return its resulting observation.

        The operation itself is immediate. A presentation client may introduce
        a delay before requesting the next action.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.models import EngineOutcome
        >>> from srd_arena.engine.queries import SessionRead
        >>> engine = Mock()
        >>> engine.read.return_value = SessionRead("intro", None, (), None, None, (), {}, {}, {}, False)
        >>> engine.advance_one_automatic_action.return_value = EngineOutcome(messages=(("Goblin", "Moves"),))
        >>> RunningGame(engine).advance_one_automatic_action().messages
        (('Goblin', 'Moves'),)
        """

        return game_update(
            self.__session,
            self.__session.advance_one_automatic_action(),
        )

    def execute(self, command: GameCommand) -> CommandResult:
        """Validate and execute one explicit interaction command.

        >>> from unittest.mock import Mock
        >>> from srd_arena.application.commands import SelectAction
        >>> from srd_arena.engine.models import EngineOutcome
        >>> from srd_arena.engine.queries import ActionOption, SessionRead
        >>> option = ActionOption("dodge", "Dodge", "action", "hero")
        >>> engine = Mock()
        >>> engine.read.return_value = SessionRead("fight", None, (option,), None, None, (), {}, {}, {}, False)
        >>> engine.choose.return_value = EngineOutcome(selected_action_id="dodge")
        >>> result = RunningGame(engine).execute(SelectAction("dodge", None))
        >>> (result.accepted, result.update.selected_action_id if result.update else None)
        (True, 'dodge')
        """

        return execute_game_command(self.__session, command)

    def reset(self) -> GameObservation:
        """Start a fresh episode of the same game.

        This supports clients that repeatedly run the same scenario, such as
        headless simulations, without reloading its authored content.

        >>> from unittest.mock import Mock
        >>> from srd_arena.engine.queries import SessionRead
        >>> engine = Mock()
        >>> engine.read.return_value = SessionRead("intro", None, (), None, None, (), {}, {}, {}, False)
        >>> RunningGame(engine).reset().scene.scene_id
        'intro'
        >>> engine.reset.assert_called_once_with()
        """

        self.__session.reset()
        return self.observe()
