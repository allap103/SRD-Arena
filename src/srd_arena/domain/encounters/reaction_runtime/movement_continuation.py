"""Resume movement after its Opportunity Attack decision closes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.geometry import MovementBudget, MovementCost, Position

from ..effect_lifecycle.movement import reconcile_remaining_movement
from ..encounter_models.decisions import PendingMovement
from ..encounter_models.resolution import EncounterProgress
from ..spatial import placement_is_free
from ..state_runtime import create_event

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
    ...     movement_remaining=MovementBudget(25),
    ...     movement_mode="walk",
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
    ...     "movement_continuation.placement_is_free", return_value=True
    ... ), patch(
    ...     "srd_arena.domain.encounters.reaction_runtime."
    ...     "movement_continuation.reconcile_remaining_movement"
    ... ):
    ...     resume_movement(state, movement, progress)
    >>> (mover.position, int(mover.movement_remaining))
    (Position(x=1, y=0), 20)
    """

    mover = state.creatures[movement.creature_ref]
    moving_refs = {movement.creature_ref, *movement.companion_destinations}
    destinations = {
        movement.creature_ref: movement.to_position,
        **movement.companion_destinations,
    }
    movement_is_affordable = (
        mover.movement_remaining is None
        or movement.movement_cost <= mover.movement_remaining
    )
    movement_completed = (
        mover.is_alive
        and movement_is_affordable
        and all(
            placement_is_free(
                state,
                moving_ref,
                destination,
                ignored_refs=moving_refs,
            )
            for moving_ref, destination in destinations.items()
        )
    )
    if movement_completed:
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
        mover.movement_mode = movement.movement_mode
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
                    "movement_mode": movement.movement_mode,
                    "to": {
                        "x": movement.to_position.x,
                        "y": movement.to_position.y,
                    },
                    "resumed": True,
                },
            )
        )
        mover.movement_remaining = MovementBudget(
            max(
                0,
                int(mover.movement_remaining or 0) - int(movement.movement_cost),
            )
        )
    elif mover.is_alive and not movement_is_affordable:
        progress.messages.append(
            (
                "system",
                f"{mover.creature.name} no longer has enough movement to move "
                f"{movement.direction}.",
            )
        )
        progress.events.append(
            create_event(
                state,
                "movement_cancelled",
                creature_ref=movement.creature_ref,
                action_id=movement.action_id,
                data={
                    "direction": movement.direction,
                    "reason": "insufficient_movement",
                    "resumed": True,
                },
            )
        )
    reconcile_remaining_movement(state, (movement.creature_ref,))
