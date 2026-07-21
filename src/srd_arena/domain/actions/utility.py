from __future__ import annotations

from typing import TYPE_CHECKING

from ..encounters.models import EncounterProgress

if TYPE_CHECKING:
    from ..encounters.encounter import EncounterState


def resolve_wait_action(
    self: EncounterState,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    progress.messages.append(("system", "You hold your ground."))
    progress.events.append(
        self._event(
            "action_resolved",
            actor_ref="player",
            action_id=action_id,
            data={"kind": "wait"},
        )
    )
