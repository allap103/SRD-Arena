"""Validate public commands and translate them into engine actions."""

from __future__ import annotations

from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.protocols import GameEngine
from srd_arena.engine.queries import (
    ActionAim,
    ActionSpellCast,
)

from .commands import (
    AimAction,
    CastSpell,
    CommandFailure,
    CommandResult,
    GameCommand,
    GameEvent,
    GameUpdate,
    SelectAction,
)
from .observations import GameObservation, observe_session
from .values import freeze_mapping


class _CommandRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def execute_game_command(
    session: GameEngine,
    command: GameCommand,
) -> CommandResult:
    """Execute a command if it still matches the advertised decision.

    A stale command is rejected before it can reach the engine.

    >>> from types import SimpleNamespace
    >>> from .gameplay_observations import capture_gameplay
    >>> from srd_arena.engine.queries import SessionRead
    >>> read = SessionRead(
    ...     scene_id="intro", action_options=(),
    ...     encounter_state=None, completion_message=None, team_ids=(),
    ...     creature_labels={}, creature_team_ids={}, item_names={},
    ...     requires_automatic_advance=False)
    >>> session = SimpleNamespace(_read=lambda: read, observe_gameplay=lambda: capture_gameplay(read))
    >>> result = execute_game_command(session, SelectAction("wait", "old"))
    >>> (result.accepted, result.failure.code)
    (False, 'stale_decision')
    """

    observation = observe_session(session)
    if command.expected_decision_id != decision_id(observation):
        return _reject(
            "stale_decision",
            "The game has advanced since this interaction was displayed.",
        )
    try:
        if isinstance(command, SelectAction):
            engine_result = _select_advertised(session, observation, command.action_id)
        elif isinstance(command, AimAction):
            engine_result = _aim_action(session, observation, command)
        elif isinstance(command, CastSpell):
            option = next(
                (
                    a
                    for a in observation.scene.action_details
                    if a.id == command.action_id and a.kind == "spell" and a.enabled
                ),
                None,
            )
            if option is None:
                raise _CommandRejected(
                    "action_unavailable", "Spell action is unavailable."
                )
            engine_result = session._configure_action(
                command.action_id,
                ActionSpellCast(command.target_refs, command.allocations, command.aim),
            )
        else:
            return _reject("unsupported_command", "Unsupported game command.")
    except _CommandRejected as error:
        return _reject(error.code, str(error))
    except (KeyError, RuntimeError, ValueError) as error:
        return _reject("command_rejected", str(error))
    return CommandResult(update=game_update(session, engine_result))


def game_update(session: GameEngine, result: EngineOutcome) -> GameUpdate:
    """Translate an accepted operation result into a public engine update.

    >>> from types import SimpleNamespace
    >>> from .gameplay_observations import capture_gameplay
    >>> from srd_arena.engine.queries import SessionRead
    >>> read = SessionRead(
    ...     scene_id="intro", action_options=(),
    ...     encounter_state=None, completion_message=None, team_ids=(),
    ...     creature_labels={}, creature_team_ids={}, item_names={},
    ...     requires_automatic_advance=False)
    >>> update = game_update(
    ...     SimpleNamespace(_read=lambda: read, observe_gameplay=lambda: capture_gameplay(read)),
    ...     EngineOutcome(selected_action_id="wait", messages=(("Hero", "Waits"),)))
    >>> (update.selected_action_id, update.messages)
    ('wait', (('Hero', 'Waits'),))
    """

    return GameUpdate(
        observation=observe_session(session),
        messages=tuple(result.messages),
        events=tuple(_observe_event(event) for event in result.events),
        selected_action_id=result.selected_action_id,
        selected_choice_text=result.selected_choice_text,
        should_exit=result.should_exit,
    )


def _observe_event(event: CombatEvent) -> GameEvent:
    return GameEvent(
        seq=event.seq,
        type=event.type,
        creature_ref=event.creature_ref,
        frame_id=event.frame_id,
        action_id=event.action_id,
        data=freeze_mapping(event.data),
    )


def decision_id(observation: GameObservation) -> str | None:
    """Return the decision token clients must echo with their next command.

    >>> from srd_arena.engine.observation_models import GameObservation, SceneObservation
    >>> observation = GameObservation(SceneObservation("intro", ()), None, None, False)
    >>> decision_id(observation) is None
    True
    """

    return (
        observation.encounter.decision.id if observation.encounter is not None else None
    )


def _select_advertised(
    session: GameEngine,
    observation: GameObservation,
    action_id: str,
) -> EngineOutcome:
    option = next(
        (
            option
            for option in observation.scene.action_details
            if option.id == action_id
        ),
        None,
    )
    if option is None or not option.enabled:
        raise _CommandRejected(
            "action_unavailable",
            f"Action '{action_id}' is not available.",
        )
    if (
        option.spell_cast is not None
        and option.spell_cast.select_targets
        and (
            option.spell_cast.maximum_targets > 1
            or option.spell_cast.resource_pool is not None
        )
    ):
        raise _CommandRejected(
            "action_configuration_required", "Submit a complete spell cast."
        )
    if option.required_configuration is not None:
        raise _CommandRejected(
            "action_configuration_required",
            f"Action '{action_id}' requires {option.required_configuration} configuration.",
        )
    return session._choose(action_id)


def _aim_action(
    session: GameEngine,
    observation: GameObservation,
    command: AimAction,
) -> EngineOutcome:
    option = next(
        (
            option
            for option in observation.scene.action_details
            if option.id == command.action_id and option.enabled
        ),
        None,
    )
    if option is None or option.required_configuration != "aim":
        raise _CommandRejected(
            "action_unavailable",
            f"Aimable action '{command.action_id}' is not available.",
        )
    return session._configure_action(
        option.id,
        ActionAim(x=command.x, y=command.y),
    )


def _reject(code: str, message: str) -> CommandResult:
    return CommandResult(failure=CommandFailure(code=code, message=message))
