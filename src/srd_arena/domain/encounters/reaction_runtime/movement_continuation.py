"""Resume movement after its Opportunity Attack decision closes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...geometry import Position
from ..models import EncounterProgress, PendingMovement

if TYPE_CHECKING:
    from ..encounter import EncounterState


def resume_movement(
    state: EncounterState,
    movement: PendingMovement,
    progress: EncounterProgress,
) -> None:
    """Resume the exact movement occurrence suspended by a reaction frame."""

    mover = state.creatures[movement.creature_ref]
    if mover.is_alive and state._position_is_free(
        movement.to_position.x,
        movement.to_position.y,
        ignored_refs={movement.creature_ref},
    ):
        mover.position = Position(
            movement.to_position.x,
            movement.to_position.y,
        )
        for target_ref, target_position in movement.companion_destinations.items():
            state.creatures[target_ref].position = Position(
                target_position.x,
                target_position.y,
            )
        progress.messages.append(
            (
                "system",
                f"{mover.creature.name} moves {movement.direction} to "
                f"({movement.to_position.x}, {movement.to_position.y}).",
            )
        )
        progress.events.append(
            state._event(
                "movement_resolved",
                creature_ref=movement.creature_ref,
                action_id=movement.action_id,
                data={
                    "direction": movement.direction,
                    "to": {
                        "x": movement.to_position.x,
                        "y": movement.to_position.y,
                    },
                    "resumed": True,
                },
            )
        )

    mover.movement_remaining = movement.remaining_movement_after

