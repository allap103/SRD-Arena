"""Mutation helpers and identifiers owned by encounter state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.application import apply_effects
from srd_arena.domain.effects.results import EffectResult

from .condition_state import apply_condition, remove_condition
from .effect_lifecycle.application import start_ongoing_effect
from .effect_lifecycle.removal import remove_ongoing_effects
from .encounter_models.actions import CreatureRef
from .encounter_models.resolution import EncounterProgress
from .event_stream import create_event as create_event

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


def merge_progress(
    _state: EncounterState,
    target: EncounterProgress,
    source: EncounterProgress,
) -> None:
    """Append messages, events, and completion from nested encounter progress.

    >>> target = EncounterProgress(messages=[("system", "Start")])
    >>> source = EncounterProgress(
    ...     messages=[("system", "Done")], completed=True,
    ...     paused_for_decision=True,
    ... )
    >>> merge_progress(None, target, source)
    >>> (target.messages, target.completed, target.paused_for_decision)
    ([('system', 'Start'), ('system', 'Done')], True, True)
    """

    target.messages.extend(source.messages)
    target.events.extend(source.events)
    target.completed = target.completed or source.completed
    target.paused_for_decision = (
        target.paused_for_decision or source.paused_for_decision
    )


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
