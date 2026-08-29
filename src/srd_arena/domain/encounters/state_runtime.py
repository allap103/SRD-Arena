"""Mutation helpers and identifiers owned by encounter state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..effects.application import apply_effects
from ..effects.results import EffectResult
from ..geometry import Position
from .condition_state import apply_condition, remove_condition
from .effect_lifecycle.application import start_ongoing_effect
from .effect_lifecycle.removal import remove_ongoing_effects
from .encounter_models.actions import CreatureRef
from .encounter_models.resolution import (
    CombatEvent,
    EncounterProgress,
)

if TYPE_CHECKING:
    from .encounter import EncounterState


def apply_encounter_effects(
    state: EncounterState,
    effects: list[EffectResult],
    *,
    origin_id: str | None = None,
) -> list[tuple[str, str]]:
    """Apply resolved conditions and ongoing effects to encounter-owned state.

    >>> from types import SimpleNamespace
    >>> effect = EffectResult(
    ...     "message", "hero", data={"channel": "combat", "text": "Hit!"}
    ... )
    >>> state = SimpleNamespace(runtime_state_sequence=1)
    >>> apply_encounter_effects(state, [effect])
    [('combat', 'Hit!')]
    """

    resolved_origin_id = origin_id or next_runtime_origin_id(state)
    return apply_effects(
        effects,
        apply_condition=lambda condition: apply_condition(state, condition),
        remove_condition=lambda target, condition: remove_condition(
            state, target, condition
        ),
        apply_ongoing_effect=lambda effect, origin: start_ongoing_effect(
            state, effect, origin
        ),
        remove_ongoing_effects=lambda effect: remove_ongoing_effects(state, effect),
        origin_id=resolved_origin_id,
    )


def next_action_id(state: EncounterState) -> str:
    """Allocate a unique action identifier within this encounter runtime.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(action_sequence=3)
    >>> (next_action_id(state), state.action_sequence)
    ('action_3', 4)
    """

    action_id = f"action_{state.action_sequence}"
    state.action_sequence += 1
    return action_id


def next_runtime_origin_id(state: EncounterState) -> str:
    """Allocate an identity for one runtime application of a rule source.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(runtime_state_sequence=2)
    >>> (next_runtime_origin_id(state), state.runtime_state_sequence)
    ('effect_2', 3)
    """

    origin_id = f"effect_{state.runtime_state_sequence}"
    state.runtime_state_sequence += 1
    return origin_id


def next_frame_id(state: EncounterState, prefix: str = "frame") -> str:
    """Allocate an identity for one invocation on the decision stack.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(frame_sequence=5)
    >>> (next_frame_id(state, "reaction"), state.frame_sequence)
    ('reaction_5', 6)
    """

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
    """Create a sequence-numbered combat event and advance the counter.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(event_sequence=7)
    >>> event = create_event(state, "turn_started", "hero")
    >>> (event.seq, event.type, event.creature_ref, state.event_sequence)
    (7, 'turn_started', 'hero', 8)
    """

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
    """Append messages, events, and transitions from nested encounter progress.

    >>> target = EncounterProgress(messages=[("system", "Start")])
    >>> source = EncounterProgress(
    ...     messages=[("system", "Done")], transition="victory",
    ...     paused_for_decision=True,
    ... )
    >>> merge_progress(None, target, source)
    >>> (target.messages, target.transition, target.paused_for_decision)
    ([('system', 'Start'), ('system', 'Done')], 'victory', True)
    """

    target.messages.extend(source.messages)
    target.events.extend(source.events)
    if source.transition is not None:
        target.transition = source.transition
    target.paused_for_decision = (
        target.paused_for_decision or source.paused_for_decision
    )
    target.paused_for_pacing = target.paused_for_pacing or source.paused_for_pacing


def creature_label(state: EncounterState, creature_ref: CreatureRef) -> str:
    """Return a user-facing label for a runtime creature reference.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(creatures={
    ...     "hero": SimpleNamespace(
    ...         creature=SimpleNamespace(name="Aria"), creature_id="wizard"
    ...     )
    ... })
    >>> creature_label(state, "hero")
    'Aria (wizard)'
    """

    creature_state = state.creatures[creature_ref]
    return f"{creature_state.creature.name} ({creature_state.creature_id})"


def living_creature_refs(state: EncounterState) -> list[CreatureRef]:
    """Return runtime references for creatures that still have hit points.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(creatures={
    ...     "hero": SimpleNamespace(is_alive=True),
    ...     "goblin": SimpleNamespace(is_alive=False),
    ... })
    >>> living_creature_refs(state)
    ['hero']
    """

    return [
        creature_ref
        for creature_ref, creature_state in state.creatures.items()
        if creature_state.is_alive
    ]


def creature_position(state: EncounterState, creature_ref: CreatureRef) -> Position:
    """Return the current grid position of a runtime creature.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(
    ...     creatures={"hero": SimpleNamespace(position=Position(2, 3))}
    ... )
    >>> creature_position(state, "hero")
    Position(x=2, y=3)
    """

    return state.creatures[creature_ref].position


def position_is_free(
    state: EncounterState,
    x: int,
    y: int,
    *,
    ignored_refs: set[CreatureRef] | frozenset[CreatureRef] = frozenset(),
) -> bool:
    """Return whether a creature may end movement at a grid position.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(
    ...     definition=SimpleNamespace(
    ...         grid=SimpleNamespace(width=5, height=5)
    ...     ),
    ...     creatures={
    ...         "hero": SimpleNamespace(is_alive=True, position=Position(2, 2))
    ...     },
    ... )
    >>> position_is_free(state, 1, 1)
    True
    >>> position_is_free(state, 2, 2)
    False
    """

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
    """Return the size category of a runtime creature.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(creatures={
    ...     "ogre": SimpleNamespace(creature=SimpleNamespace(size="L"))
    ... })
    >>> creature_size(state, "ogre")
    'L'
    """

    return state.creatures[creature_ref].creature.size
