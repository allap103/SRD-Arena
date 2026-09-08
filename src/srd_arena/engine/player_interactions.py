"""Validate commands against player-relative observations."""

from __future__ import annotations

from .commands import (
    AimAction,
    CancelTargeting,
    ChangeTarget,
    CommandFailure,
    ConfirmTargeting,
    GameCommand,
    GameUpdate,
    PlayerCommandResult,
    PlayerGameUpdate,
    SelectAction,
    SetResourceAllocation,
)
from .interactions import execute_game_command
from .models import EngineOutcome
from .player_observation_models import CreatureAllegiance, PlayerObservation
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
    if not any(
        creature.creature_ref == observation.decision.creature_ref
        and creature.allegiance is CreatureAllegiance.ALLY
        for creature in observation.creatures
    ):
        return _reject("decision_not_owned", "This decision belongs to another team.")
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
            update = player_game_update(
                session,
                perspective_team_id,
                session._choose_player_action(command.action_id),
            )
        except KeyError, RuntimeError, ValueError:
            return _reject(
                "command_rejected", "The requested action could not be applied."
            )
        return PlayerCommandResult(update=update)

    if not _configuration_is_advertised(observation, command):
        return _reject(
            "action_unavailable", "The requested configuration is not available."
        )
    result = execute_game_command(session, command)
    if result.failure is not None:
        return _reject(
            "command_rejected", "The requested configuration could not be applied."
        )
    assert result.update is not None
    return PlayerCommandResult(
        update=_player_update(session, perspective_team_id, result.update)
    )


def _configuration_is_advertised(
    observation: PlayerObservation,
    command: GameCommand,
) -> bool:
    """Require player-visible options before privileged configuration validation.

    Enemy resource allocations remain excluded until their bounds can be checked
    without revealing private health through accepted/rejected amounts.
    """

    options = tuple(action for action in observation.action_details if action.enabled)
    if isinstance(command, AimAction):
        return any(
            action.id == command.action_id and action.required_configuration == "aim"
            for action in options
        )
    if isinstance(command, ChangeTarget):
        return any(
            action.kind == "toggle_spell_target"
            and action.target_ref == command.target_ref
            and (
                command.source_trigger_id is None
                or action.source_trigger_id == command.source_trigger_id
            )
            for action in options
        )
    if isinstance(command, SetResourceAllocation):
        return any(
            creature.creature_ref == command.target_ref
            and creature.allegiance is CreatureAllegiance.ALLY
            for creature in observation.creatures
        ) and any(
            action.kind == "set_spell_resource_allocation"
            and action.target_ref == command.target_ref
            for action in options
        )
    if isinstance(command, (ConfirmTargeting, CancelTargeting)):
        kind = (
            "confirm_spell_targets"
            if isinstance(command, ConfirmTargeting)
            else "cancel_spell_targets"
        )
        return any(action.kind == kind for action in options)
    return False


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


def player_game_update(
    session: PlayerGameEngine,
    perspective_team_id: str,
    outcome: EngineOutcome,
) -> PlayerGameUpdate:
    """Translate an engine outcome directly into a player-safe update."""

    return PlayerGameUpdate(
        observation=session.observe_player(perspective_team_id),
        messages=(),
        events=(),
        selected_action_id=outcome.selected_action_id,
        selected_choice_text=outcome.selected_choice_text,
        should_exit=outcome.should_exit,
    )


def _reject(code: str, message: str) -> PlayerCommandResult:
    return PlayerCommandResult(failure=CommandFailure(code, message))
