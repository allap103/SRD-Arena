"""Resume movement after its Opportunity Attack decision closes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.geometry import MovementCost, Position

from ..encounter_models.decisions import PendingMovement
from ..encounter_models.resolution import EncounterProgress
from ..state_runtime import create_event, position_is_free

if TYPE_CHECKING:
    from ..encounter import EncounterState


def resume_movement(
    state: EncounterState,
    movement: PendingMovement,
    progress: EncounterProgress,
) -> None:
    """Resume the exact movement occurrence suspended by a reaction frame.

    >>> from types import SimpleNamespace
    >>> mover = SimpleNamespace(
    ...     is_alive=True,
    ...     position=Position(0, 0),
    ...     movement_spent_this_turn=MovementCost(5),
    ...     movement_remaining=None,
    ...     creature=SimpleNamespace(name="Hero"),
    ... )
    >>> movement = PendingMovement(
    ...     "move-1", "hero", "right", Position(0, 0), Position(1, 0),
    ...     20, MovementCost(5), "trigger-1",
    ... )
    >>> state = SimpleNamespace(creatures={"hero": mover}, event_sequence=1)
    >>> progress = EncounterProgress()
    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.reaction_runtime."
    ...     "movement_continuation.position_is_free", return_value=True
    ... ):
    ...     resume_movement(state, movement, progress)
    >>> (mover.position, int(mover.movement_remaining))
    (Position(x=1, y=0), 20)
    """

    mover = state.creatures[movement.creature_ref]
    if mover.is_alive and position_is_free(
        state,
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
        mover.movement_spent_this_turn = MovementCost(
            int(mover.movement_spent_this_turn) + int(movement.movement_cost)
        )
        progress.messages.append(
            (
                "system",
                f"{mover.creature.name} moves {movement.direction} to "
                f"({movement.to_position.x}, {movement.to_position.y}).",
            )
        )
        progress.events.append(
            create_event(
                state,
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
