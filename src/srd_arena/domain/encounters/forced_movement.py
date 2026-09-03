"""Resolve movement imposed by an effect without spending a creature's Speed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.runtime import RelationshipKind
from srd_arena.domain.geometry import Position, grid_distance_between

from .condition_state import remove_condition_from_source
from .encounter_models.actions import CreatureRef
from .spatial import (
    creature_occupied_cells,
    creatures_are_adjacent,
    diagonal_terrain_step_is_clear,
    placement_is_free,
)

if TYPE_CHECKING:
    from .encounter import EncounterState

ForcedMovementDirection = Literal["away", "toward"]


@dataclass(frozen=True)
class ForcedMovementResult:
    """Report the traversed path and grapple relationships ended by a push or pull."""

    target_ref: CreatureRef
    start: Position
    path: tuple[Position, ...]
    requested_steps: int
    ended_grapples: tuple[tuple[CreatureRef, CreatureRef], ...] = ()

    @property
    def end(self) -> Position:
        """Return the target's final anchor position."""

        return self.path[-1] if self.path else self.start

    @property
    def moved_steps(self) -> int:
        """Return how many grid cells the target actually traversed."""

        return len(self.path)

    @property
    def blocked(self) -> bool:
        """Return whether an obstacle stopped movement before the requested distance."""

        return self.moved_steps < self.requested_steps


def forced_movement_path(
    state: EncounterState,
    source_ref: CreatureRef,
    target_ref: CreatureRef,
    direction: ForcedMovementDirection,
    maximum_steps: int,
) -> tuple[Position, ...]:
    """Return the legal consecutive anchors for an imposed push or pull.

    The path ignores movement costs and does not offer Opportunity Attacks. It
    stops at the first occupied, out-of-bounds, or blocked destination and uses
    the same complete-footprint placement rules as voluntary movement.
    """

    if maximum_steps < 0:
        raise ValueError("Forced movement distance cannot be negative.")
    dx, dy = _relative_step(state, source_ref, target_ref, direction)
    current = state.creatures[target_ref].position
    path: list[Position] = []
    for _ in range(maximum_steps):
        destination = Position(current.x + dx, current.y + dy)
        if not diagonal_terrain_step_is_clear(
            state,
            target_ref,
            current,
            destination,
        ) or not placement_is_free(
            state,
            target_ref,
            destination,
            ignored_refs={target_ref},
        ):
            break
        path.append(destination)
        current = destination
    return tuple(path)


def apply_forced_movement(
    state: EncounterState,
    source_ref: CreatureRef,
    target_ref: CreatureRef,
    direction: ForcedMovementDirection,
    steps: int,
) -> ForcedMovementResult:
    """Move a target along its legal forced path and end separated grapples."""

    start = state.creatures[target_ref].position
    path = forced_movement_path(state, source_ref, target_ref, direction, steps)
    if path:
        state.creatures[target_ref].position = path[-1]
    ended_grapples = _end_separated_grapples(state, target_ref) if path else ()
    return ForcedMovementResult(
        target_ref=target_ref,
        start=start,
        path=path,
        requested_steps=steps,
        ended_grapples=ended_grapples,
    )


def _relative_step(
    state: EncounterState,
    source_ref: CreatureRef,
    target_ref: CreatureRef,
    direction: ForcedMovementDirection,
) -> tuple[int, int]:
    source, target = min(
        (
            (source_cell, target_cell)
            for source_cell in creature_occupied_cells(state, source_ref)
            for target_cell in creature_occupied_cells(state, target_ref)
        ),
        key=lambda cells: (
            grid_distance_between(*cells),
            abs(cells[1].x - cells[0].x) + abs(cells[1].y - cells[0].y),
            cells[0].y,
            cells[0].x,
            cells[1].y,
            cells[1].x,
        ),
    )
    dx = _sign(target.x - source.x)
    dy = _sign(target.y - source.y)
    if direction == "toward":
        dx, dy = -dx, -dy
    if dx == 0 and dy == 0:
        raise ValueError("Forced movement requires distinct source and target spaces.")
    return dx, dy


def _end_separated_grapples(
    state: EncounterState,
    moved_ref: CreatureRef,
) -> tuple[tuple[CreatureRef, CreatureRef], ...]:
    separated = tuple(
        (relationship.source_ref, relationship.target_ref)
        for relationship in state.relationships
        if relationship.kind is RelationshipKind.GRAPPLING
        and moved_ref in {relationship.source_ref, relationship.target_ref}
        and not creatures_are_adjacent(
            state,
            relationship.source_ref,
            relationship.target_ref,
        )
    )
    for source_ref, target_ref in separated:
        remove_condition_from_source(
            state,
            target_ref,
            Condition.GRAPPLED,
            source_ref=source_ref,
        )
    return separated


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)
