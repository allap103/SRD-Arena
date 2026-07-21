from __future__ import annotations

from typing import TYPE_CHECKING

from ..combat.models import EncounterProgress

if TYPE_CHECKING:
    from ..combat.encounter import EncounterState


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


def resolve_flee_action(
    self: EncounterState,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    progress.messages.append(("system", "You flee the encounter."))
    progress.transition = self.definition.flee.next_scene if self.definition.flee else None
    progress.events.append(
        self._event(
            "action_resolved",
            actor_ref="player",
            action_id=action_id,
            data={"kind": "flee"},
        )
    )
