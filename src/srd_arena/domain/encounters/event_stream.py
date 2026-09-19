"""Create ordered combat events without depending on encounter mutation helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .encounter_models.actions import CreatureRef
from .encounter_models.resolution import CombatEvent

if TYPE_CHECKING:
    from .encounter import EncounterState


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

    # Imported here to avoid the encounter/query module initialization cycle.
    from .event_visibility import event_visibility

    event = CombatEvent(
        seq=state.event_sequence,
        type=event_type,
        creature_ref=creature_ref,
        frame_id=frame_id,
        action_id=action_id,
        data=data or {},
        visible_by_team=(
            event_visibility(state)
            if getattr(state, "capture_event_visibility", False) is True
            else None
        ),
    )
    state.event_sequence += 1
    return event
