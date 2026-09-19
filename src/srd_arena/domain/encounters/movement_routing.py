"""Find reusable obstacle-aware routes across the encounter grid."""

from __future__ import annotations

from collections import deque
from heapq import heappop, heappush
from itertools import count
from typing import TYPE_CHECKING

from srd_arena.domain.geometry import Position

from .behaviors import DIRECTION_DELTAS
from .encounter_models.actions import CreatureRef
from .grappling_state import grappling_targets_for
from .rule_queries.movement import movement_step_cost
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


def farthest_retreat_directions(
    state: EncounterState,
    mover_ref: CreatureRef,
    target_ref: CreatureRef,
    *,
    movement_budget: int,
) -> frozenset[str]:
    """Return first steps of routes ending farthest away within a movement budget.

    Search costs include Difficult Terrain, crawling, and grapple dragging. A
    route may move laterally around an obstacle but never reduce its distance
    from the target whose position defines "away."
    """

    if movement_budget < 0:
        raise ValueError("Retreat movement budget cannot be negative.")
    if (
        movement_budget == 0
        or mover_ref not in state.creatures
        or target_ref not in state.creatures
        or target_ref in grappling_targets_for(state, mover_ref)
    ):
        return frozenset()

    start = creature_position(state, mover_ref)
    initial_distance = int(creature_distance(state, mover_ref, target_ref))
    sequence = count()
    frontier: list[tuple[int, int, Position, str | None]] = [
        (0, next(sequence), start, None)
    ]
    best_costs: dict[tuple[int, int, str | None], int] = {(start.x, start.y, None): 0}
    farthest_distance = initial_distance
    first_steps: set[str] = set()

    while frontier:
        spent, _order, current, first_step = heappop(frontier)
        state_key = (current.x, current.y, first_step)
        if spent != best_costs.get(state_key):
            continue
        current_distance = int(
            creature_distance(
                state,
                mover_ref,
                target_ref,
                source_position=current,
            )
        )
        for direction, (dx, dy) in DIRECTION_DELTAS.items():
            destination = Position(current.x + dx, current.y + dy)
            if not _route_step_is_clear(state, mover_ref, current, destination):
                continue
            destination_distance = int(
                creature_distance(
                    state,
                    mover_ref,
                    target_ref,
                    source_position=destination,
                )
            )
            if destination_distance < current_distance:
                continue
            next_spent = spent + int(movement_step_cost(state, mover_ref, destination))
            if next_spent > movement_budget:
                continue
            route_first_step = first_step or direction
            destination_key = (
                destination.x,
                destination.y,
                route_first_step,
            )
            if next_spent >= best_costs.get(destination_key, movement_budget + 1):
                continue
            best_costs[destination_key] = next_spent
            heappush(
                frontier,
                (next_spent, next(sequence), destination, route_first_step),
            )
            if destination_distance > farthest_distance:
                farthest_distance = destination_distance
                first_steps = {route_first_step}
            elif (
                destination_distance == farthest_distance
                and farthest_distance > initial_distance
            ):
                first_steps.add(route_first_step)

    return frozenset(first_steps)


def _route_step_is_clear(
    state: EncounterState,
    mover_ref: CreatureRef,
    source: Position,
    destination: Position,
) -> bool:
    dx = destination.x - source.x
    dy = destination.y - source.y
    mover_origin = creature_position(state, mover_ref)
    moving_refs = {mover_ref, *grappling_targets_for(state, mover_ref)}
    simulated_sources = {
        moving_ref: Position(
            creature_position(state, moving_ref).x + source.x - mover_origin.x,
            creature_position(state, moving_ref).y + source.y - mover_origin.y,
        )
        for moving_ref in moving_refs
    }
    simulated_destinations = {
        moving_ref: Position(
            simulated_source.x + dx,
            simulated_source.y + dy,
        )
        for moving_ref, simulated_source in simulated_sources.items()
    }
    return all(
        diagonal_terrain_step_is_clear(
            state,
            moving_ref,
            simulated_sources[moving_ref],
            simulated_destinations[moving_ref],
        )
        and placement_is_free(
            state,
            moving_ref,
            simulated_destinations[moving_ref],
            ignored_refs=moving_refs,
        )
        for moving_ref in moving_refs
    )
