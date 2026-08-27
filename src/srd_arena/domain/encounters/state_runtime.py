"""Mutation helpers and identifiers owned by encounter state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..effects.application import apply_effects
from ..effects.results import EffectResult
from ..geometry import MovementBudget, Position
from .models import CombatEvent, CreatureRef, EncounterProgress
from .ongoing_effects import remove_ongoing_effects

if TYPE_CHECKING:
    from .encounter import EncounterState


def apply_encounter_effects(
    state: EncounterState,
    effects: list[EffectResult],
    *,
    origin_id: str | None = None,
) -> list[tuple[str, str]]:
    """Apply resolved conditions and ongoing effects to encounter-owned state."""

    resolved_origin_id = origin_id or state._next_runtime_origin_id()
    return apply_effects(
        effects,
        apply_condition=state._apply_condition,
        remove_condition=state._remove_condition,
        apply_ongoing_effect=state._start_ongoing_effect,
        remove_ongoing_effects=lambda effect: remove_ongoing_effects(state, effect),
        origin_id=resolved_origin_id,
    )


def consume_action(state: EncounterState, *, allow_magic: bool) -> None:
    """Spend the active creature's Action while enforcing magic-action restrictions."""

    if state.active_actions_remaining <= 0:
        raise RuntimeError("No Action remains to consume.")
    non_magic_only_actions = max(
        0,
        state.active_actions_remaining - state.active_magic_actions_remaining,
    )
    if allow_magic:
        if state.active_magic_actions_remaining <= 0:
            raise RuntimeError("No spell-capable Action remains to consume.")
        state.active_magic_actions_remaining -= 1
    elif non_magic_only_actions <= 0 and state.active_magic_actions_remaining > 0:
        state.active_magic_actions_remaining -= 1
    state.active_actions_remaining -= 1


def active_movement_remaining(state: EncounterState) -> MovementBudget:
    """Return the active creature's remaining movement in grid cells."""

    return state.active_movement_remaining_for()


def next_action_id(state: EncounterState) -> str:
    """Allocate a unique action identifier within this encounter runtime."""

    action_id = f"action_{state.action_sequence}"
    state.action_sequence += 1
    return action_id


def next_runtime_origin_id(state: EncounterState) -> str:
    """Allocate an identity for one runtime application of a rule source."""

    origin_id = f"effect_{state.runtime_state_sequence}"
    state.runtime_state_sequence += 1
    return origin_id


def next_frame_id(state: EncounterState, prefix: str = "frame") -> str:
    """Allocate an identity for one invocation on the decision stack."""

    frame_id = f"{prefix}_{state.frame_sequence}"
    state.frame_sequence += 1
    return frame_id


def create_event(
    state: EncounterState,
    event_type: str,
    creature_ref: CreatureRef | None = None,
    frame_id: str | None = None,
    action_id: str | None = None,
    data: dict[str, object] | None = None,
) -> CombatEvent:
    """Append a sequence-numbered combat event and return the stored event."""

    event = CombatEvent(
        seq=state.event_sequence,
        type=event_type,
        creature_ref=creature_ref,
        frame_id=frame_id,
        action_id=action_id,
        data=data or {},
    )
    state.event_sequence += 1
    return event


def merge_progress(
    _state: EncounterState,
    target: EncounterProgress,
    source: EncounterProgress,
) -> None:
    """Append messages, events, and transitions from nested encounter progress."""

    target.messages.extend(source.messages)
    target.events.extend(source.events)
    if source.transition is not None:
        target.transition = source.transition
    target.paused_for_decision = (
        target.paused_for_decision or source.paused_for_decision
    )
    target.paused_for_pacing = target.paused_for_pacing or source.paused_for_pacing


def creature_label(state: EncounterState, creature_ref: CreatureRef) -> str:
    """Return a user-facing label for a runtime creature reference."""

    creature_state = state.creatures[creature_ref]
    return f"{creature_state.creature.name} ({creature_state.creature_id})"


def living_creature_refs(state: EncounterState) -> list[CreatureRef]:
    """Return runtime references for creatures that still have hit points."""

    return [
        creature_ref
        for creature_ref, creature_state in state.creatures.items()
        if creature_state.is_alive
    ]


def creature_position(state: EncounterState, creature_ref: CreatureRef) -> Position:
    """Return the current grid position of a runtime creature."""

    return state.creatures[creature_ref].position


def position_is_free(
    state: EncounterState,
    x: int,
    y: int,
    *,
    ignored_refs: set[CreatureRef] | frozenset[CreatureRef] = frozenset(),
) -> bool:
    """Return whether a creature may end movement at a grid position."""

    if (
        x < 0
        or y < 0
        or x >= state.definition.grid.width
        or y >= state.definition.grid.height
    ):
        return False
    for creature_ref, creature_state in state.creatures.items():
        if creature_ref in ignored_refs or not creature_state.is_alive:
            continue
        if creature_state.position.x == x and creature_state.position.y == y:
            return False
    return True


def creature_size(state: EncounterState, creature_ref: CreatureRef) -> str:
    """Return the size category of a runtime creature."""

    return state.creatures[creature_ref].creature.size
