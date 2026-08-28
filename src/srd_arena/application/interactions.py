"""Validate application commands and translate them into engine actions."""

from __future__ import annotations

from srd_arena.domain.encounters.models import CombatEvent
from srd_arena.engine.api import GameEngine
from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.queries import ActionAim, ActionResourceAllocation

from .commands import (
    AimAction,
    CancelTargeting,
    ChangeTarget,
    CommandFailure,
    CommandResult,
    ConfirmTargeting,
    GameCommand,
    GameEvent,
    GameUpdate,
    SelectAction,
    SetResourceAllocation,
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
    >>> from srd_arena.engine.queries import SessionRead
    >>> read = SessionRead(
    ...     scene_id="intro", scene_text=None, action_options=(),
    ...     encounter_state=None, transition_message=None, team_ids=(),
    ...     creature_labels={}, creature_team_ids={}, item_names={},
    ...     requires_automatic_advance=False)
    >>> session = SimpleNamespace(read=lambda: read)
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
        elif isinstance(command, ChangeTarget):
            engine_result = _change_target(session, observation, command)
        elif isinstance(command, SetResourceAllocation):
            engine_result = _set_resource_allocation(session, observation, command)
        elif isinstance(command, ConfirmTargeting):
            engine_result = _select_kind(session, observation, "confirm_spell_targets")
        elif isinstance(command, CancelTargeting):
            engine_result = _select_kind(session, observation, "cancel_spell_targets")
        else:
            return _reject("unsupported_command", "Unsupported game command.")
    except _CommandRejected as error:
        return _reject(error.code, str(error))
    except (KeyError, RuntimeError, ValueError) as error:
        return _reject("command_rejected", str(error))
    return CommandResult(update=game_update(session, engine_result))


def game_update(session: GameEngine, result: EngineOutcome) -> GameUpdate:
    """Translate an accepted engine result into an application update.

    >>> from types import SimpleNamespace
    >>> from srd_arena.engine.queries import SessionRead
    >>> read = SessionRead(
    ...     scene_id="intro", scene_text=None, action_options=(),
    ...     encounter_state=None, transition_message=None, team_ids=(),
    ...     creature_labels={}, creature_team_ids={}, item_names={},
    ...     requires_automatic_advance=False)
    >>> update = game_update(
    ...     SimpleNamespace(read=lambda: read),
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
        scene_changed=result.scene_changed,
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

    >>> from srd_arena.application.observation_models import GameObservation, SceneObservation
    >>> observation = GameObservation(SceneObservation("intro", None, ()), None, None, False)
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
    return session.choose(action_id)


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
    if option is None or option.kind not in {"spell", "stat_block"}:
        raise _CommandRejected(
            "action_unavailable",
            f"Aimable action '{command.action_id}' is not available.",
        )
    return session.configure_action(
        option.id,
        ActionAim(x=command.x, y=command.y),
    )


def _change_target(
    session: GameEngine,
    observation: GameObservation,
    command: ChangeTarget,
) -> EngineOutcome:
    encounter = observation.encounter
    if encounter is None or encounter.targeting is None:
        raise _CommandRejected(
            "targeting_not_active",
            "No staged target selection is active.",
        )
    selected = encounter.targeting.selected_target_refs.count(command.target_ref)
    if command.remove and selected == 0:
        raise _CommandRejected(
            "target_not_selected",
            "The target has no allocation to remove.",
        )
    candidates = [
        option
        for option in observation.scene.action_details
        if option.kind == "toggle_spell_target"
        and option.target_ref == command.target_ref
        and option.enabled
        and (
            command.source_trigger_id is None
            or option.source_trigger_id == command.source_trigger_id
        )
    ]
    if encounter.targeting.repeat_target_allocations:
        option = next(
            (
                candidate
                for candidate in candidates
                if candidate.id.endswith("-remove" if command.remove else "-add")
            ),
            None,
        )
    else:
        requested_state_change = (command.remove and selected > 0) or (
            not command.remove and selected == 0
        )
        option = candidates[0] if candidates and requested_state_change else None
    if option is None:
        raise _CommandRejected(
            "target_change_unavailable",
            "The requested target change is not available.",
        )
    return session.choose(option.id)


def _set_resource_allocation(
    session: GameEngine,
    observation: GameObservation,
    command: SetResourceAllocation,
) -> EngineOutcome:
    encounter = observation.encounter
    targeting = encounter.targeting if encounter is not None else None
    if targeting is None or targeting.resource_pool_total is None:
        raise _CommandRejected(
            "allocation_not_active",
            "No staged resource allocation is active.",
        )
    limit = next(
        (
            item.maximum
            for item in targeting.resource_limits
            if item.target_ref == command.target_ref
        ),
        None,
    )
    other_total = sum(
        item.amount
        for item in targeting.resource_allocations
        if item.target_ref != command.target_ref
    )
    if (
        limit is None
        or command.amount < 0
        or command.amount > limit
        or other_total + command.amount > targeting.resource_pool_total
    ):
        raise _CommandRejected(
            "invalid_allocation",
            "The requested allocation is outside its legal range.",
        )
    option = next(
        (
            option
            for option in observation.scene.action_details
            if option.kind == "set_spell_resource_allocation"
            and option.enabled
            and option.target_ref == command.target_ref
        ),
        None,
    )
    if option is None:
        raise _CommandRejected(
            "allocation_target_unavailable",
            "The requested allocation target is not available.",
        )
    return session.configure_action(
        option.id,
        ActionResourceAllocation(
            target_ref=command.target_ref,
            amount=command.amount,
        ),
    )


def _select_kind(
    session: GameEngine,
    observation: GameObservation,
    kind: str,
) -> EngineOutcome:
    option = next(
        (
            option
            for option in observation.scene.action_details
            if option.kind == kind and option.enabled
        ),
        None,
    )
    if option is None:
        raise _CommandRejected(
            "action_unavailable",
            f"No '{kind}' action is available.",
        )
    return session.choose(option.id)


def _reject(code: str, message: str) -> CommandResult:
    return CommandResult(failure=CommandFailure(code=code, message=message))
