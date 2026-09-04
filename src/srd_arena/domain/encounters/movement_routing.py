"""Find reusable obstacle-aware routes across the encounter grid."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from srd_arena.domain.geometry import Position

from .behaviors import DIRECTION_DELTAS
from .encounter_models.actions import CreatureRef
from .spatial import (
    creature_distance,
    creature_position,
    diagonal_terrain_step_is_clear,
    placement_is_free,
)

if TYPE_CHECKING:
    from .encounter import EncounterState


def shortest_approach_directions(
    state: EncounterState,
    mover_ref: CreatureRef,
    target_ref: CreatureRef,
    *,
    desired_distance: int = 1,
) -> frozenset[str]:
    """Return first steps belonging to a shortest legal route toward a target.

    Routes count orthogonal and diagonal steps equally, matching square-grid
    range. Every proposed anchor uses the shared footprint, occupancy, blocked
    terrain, and diagonal-corner rules. The query ignores the mover's remaining
    Speed because it describes the route across successive turns or decisions.
    """

    if desired_distance < 0:
        raise ValueError("Desired approach distance cannot be negative.")
    if mover_ref not in state.creatures or target_ref not in state.creatures:
        return frozenset()

    start = creature_position(state, mover_ref)
    if creature_distance(state, mover_ref, target_ref) <= desired_distance:
        return frozenset()

    frontier: deque[tuple[Position, str | None, int]] = deque([(start, None, 0)])
    visited: set[tuple[int, int, str | None]] = {(start.x, start.y, None)}
    first_steps: set[str] = set()
    shortest_length: int | None = None

    while frontier:
        current, first_step, distance_traveled = frontier.popleft()
        if shortest_length is not None and distance_traveled >= shortest_length:
            continue
        for direction, (dx, dy) in DIRECTION_DELTAS.items():
            destination = Position(current.x + dx, current.y + dy)
            route_first_step = first_step or direction
            state_key = (destination.x, destination.y, route_first_step)
            if state_key in visited:
                continue
            if not _route_step_is_clear(state, mover_ref, current, destination):
                continue
            visited.add(state_key)

            next_distance = distance_traveled + 1
            if (
                creature_distance(
                    state,
                    mover_ref,
                    target_ref,
                    source_position=destination,
                )
                <= desired_distance
            ):
                if shortest_length is None:
                    shortest_length = next_distance
                if next_distance == shortest_length:
                    first_steps.add(route_first_step)
                continue
            frontier.append((destination, route_first_step, next_distance))

    return frozenset(first_steps)


def _route_step_is_clear(
    state: EncounterState,
    mover_ref: CreatureRef,
    source: Position,
    destination: Position,
) -> bool:
    return diagonal_terrain_step_is_clear(
        state,
        mover_ref,
        source,
        destination,
    ) and placement_is_free(
        state,
        mover_ref,
        destination,
        ignored_refs={mover_ref},
    )
