"""Describe advertised one-cell movement without probing hidden game state."""

from dataclasses import dataclass

from srd_arena.domain.encounters.behaviors import DIRECTION_DELTAS

from .observation_models import ActionObservation, PositionObservation


@dataclass(frozen=True)
class MovementStepObservation:
    """One step: coordinates/displacement in cells, cost in grid movement units.

    A diagonal step changes both coordinates but normally costs one unit.
    Destination is unknown when the actor's current position is undisclosed.
    Cost comes from the advertised action, including terrain/crawling modifiers.
    This describes an attempt, not a guarantee that the destination is free.
    """

    displacement: tuple[int, int]
    destination: PositionObservation | None
    cost: int | None


def movement_step(
    action: ActionObservation, position: PositionObservation | None
) -> MovementStepObservation | None:
    """Use typed direction and cost; never infer semantics from IDs or labels."""
    if action.kind != "move" or action.movement_direction not in DIRECTION_DELTAS:
        return None
    dx, dy = DIRECTION_DELTAS[action.movement_direction]
    return MovementStepObservation(
        (dx, dy),
        PositionObservation(position.x + dx, position.y + dy) if position else None,
        action.cost.get("movement"),
    )
