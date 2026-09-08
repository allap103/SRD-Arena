"""Validate commands against player-relative observations."""

from __future__ import annotations

from .commands import (
    CommandFailure,
    GameCommand,
    GameUpdate,
    PlayerCommandResult,
    PlayerGameUpdate,
    SelectAction,
)
from .interactions import execute_game_command, game_update
from .protocols import PlayerGameEngine


def execute_player_game_command(
    session: PlayerGameEngine,
    perspective_team_id: str,
    command: GameCommand,
) -> PlayerCommandResult:
    """Execute a command without returning a privileged game observation."""

    observation = session.observe_player(perspective_team_id)
    if command.expected_decision_id != observation.decision.id:
        return _reject(
            "stale_decision",
            "The game has advanced since this interaction was displayed.",
        )
    if isinstance(command, SelectAction):
        option = next(
            (
                candidate
                for candidate in observation.action_details
                if candidate.id == command.action_id and candidate.enabled
            ),
            None,
        )
        if option is None:
            return _reject(
                "action_unavailable",
                f"Action '{command.action_id}' is not available.",
            )
        if option.required_configuration is not None:
            return _reject(
                "action_configuration_required",
                f"Action '{command.action_id}' requires "
                f"{option.required_configuration} configuration.",
            )
        try:
            update = game_update(
                session,
                session._choose_player_action(command.action_id),
            )
        except (KeyError, RuntimeError, ValueError) as error:
            return _reject("command_rejected", str(error))
        return PlayerCommandResult(
            update=_player_update(session, perspective_team_id, update)
        )

    result = execute_game_command(session, command)
    if result.failure is not None:
        return PlayerCommandResult(failure=result.failure)
    assert result.update is not None
    return PlayerCommandResult(
        update=_player_update(session, perspective_team_id, result.update)
    )


def _player_update(
    session: PlayerGameEngine,
    perspective_team_id: str,
    update: GameUpdate,
) -> PlayerGameUpdate:
    # Raw engine events and presentation messages can contain private roll,
    # defense, or failure details. A later public-event projector may populate
    # these fields; the player boundary must remain closed until then.
    return PlayerGameUpdate(
        observation=session.observe_player(perspective_team_id),
        messages=(),
        events=(),
        selected_action_id=update.selected_action_id,
        selected_choice_text=update.selected_choice_text,
        should_exit=update.should_exit,
    )


def _reject(code: str, message: str) -> PlayerCommandResult:
    return PlayerCommandResult(failure=CommandFailure(code, message))
