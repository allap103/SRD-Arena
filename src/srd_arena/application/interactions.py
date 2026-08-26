"""Validate application commands and translate them into engine actions."""

from __future__ import annotations

from srd_arena.domain.encounters.models import (
    ActionCost,
    CombatEvent,
    EncounterAction,
)
from srd_arena.domain.geometry import MovementCost
from srd_arena.domain.spells.rules import spell_action_value
from srd_arena.runtime.models import TurnResult
from srd_arena.runtime.session import Session

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
from .observations import ActionObservation, GameObservation, observe_session
from .values import freeze_mapping


class _CommandRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def execute_game_command(session: Session, command: GameCommand) -> CommandResult:
    """Execute a command if it still matches the advertised decision."""

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


def game_update(session: Session, result: TurnResult) -> GameUpdate:
    """Translate an accepted engine result into an application update."""

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
    return (
        observation.encounter.decision.id if observation.encounter is not None else None
    )


def _select_advertised(
    session: Session,
    observation: GameObservation,
    action_id: str,
) -> TurnResult:
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
    session: Session,
    observation: GameObservation,
    command: AimAction,
) -> TurnResult:
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
    value: str | tuple[float, float]
    if option.kind == "spell":
        spell_id = option.source_id
        if spell_id is None:
            raise _CommandRejected(
                "action_unavailable",
                f"Spell action '{command.action_id}' has no source identifier.",
            )
        value = spell_action_value(
            spell_id,
            aim_point=(command.x, command.y),
            slot_level=option.resource_level,
        )
    else:
        value = (command.x, command.y)
    return session.choose_encounter_action(_encounter_action(option, value=value))


def _change_target(
    session: Session,
    observation: GameObservation,
    command: ChangeTarget,
) -> TurnResult:
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
    session: Session,
    observation: GameObservation,
    command: SetResourceAllocation,
) -> TurnResult:
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
    return session.choose_encounter_action(
        _encounter_action(
            option,
            value=f"{command.target_ref}~{command.amount}",
        )
    )


def _select_kind(
    session: Session,
    observation: GameObservation,
    kind: str,
) -> TurnResult:
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


def _encounter_action(
    option: ActionObservation,
    *,
    value: str | tuple[float, float],
) -> EncounterAction:
    return EncounterAction(
        label=option.label,
        kind=option.kind,
        value=value,
        id=option.id,
        creature_ref=option.creature_ref,
        cost=ActionCost(
            movement=MovementCost(option.cost.get("movement", 0)),
            action=option.cost.get("action", 0),
            bonus_action=option.cost.get("bonus_action", 0),
            reaction=option.cost.get("reaction", 0),
        ),
        source_trigger_id=option.source_trigger_id,
        preferred_attack_type=option.preferred_attack_type,
        preferred_attack_name=option.preferred_attack_name,
    )


def _reject(code: str, message: str) -> CommandResult:
    return CommandResult(failure=CommandFailure(code=code, message=message))
