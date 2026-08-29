"""Publish one stable result shape for actions rejected during execution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from ..encounter_models.resolution import (
    ActionRejection,
    EncounterProgress,
)
from ..state_runtime import create_event

if TYPE_CHECKING:
    from ..encounter import EncounterState


def reject_action(
    state: EncounterState,
    progress: EncounterProgress,
    *,
    actor_ref: str,
    action_id: str,
    action_kind: str,
    message: str,
    reason_code: str,
    details: Mapping[str, object] | None = None,
) -> ActionRejection:
    """Record a readable message and structured event for one rejection.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(event_sequence=1)
    >>> progress = EncounterProgress()
    >>> rejection = reject_action(
    ...     state, progress, actor_ref="hero", action_id="action-1",
    ...     action_kind="attack", message="The target moved.",
    ...     reason_code="target_out_of_range",
    ...     details={"target_ref": "goblin"},
    ... )
    >>> (progress.messages[-1], progress.events[-1].data["reason_code"])
    (('system', 'The target moved.'), 'target_out_of_range')
    >>> rejection.details["target_ref"]
    'goblin'
    """

    rejection = ActionRejection(
        actor_ref=actor_ref,
        action_id=action_id,
        action_kind=action_kind,
        message=message,
        reason_code=reason_code,
        details=details or {},
    )
    event_data: dict[str, object] = dict(rejection.details)
    event_data.update(
        {
            "kind": action_kind,
            "success": False,
            "reason_code": reason_code,
            "reason": message,
        }
    )
    progress.messages.append(("system", message))
    progress.events.append(
        create_event(
            state,
            "action_resolved",
            creature_ref=actor_ref,
            action_id=action_id,
            data=event_data,
        )
    )
    return rejection
