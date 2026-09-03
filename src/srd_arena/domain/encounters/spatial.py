"""Answer encounter spatial questions from complete creature footprints."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from typing import TYPE_CHECKING

from srd_arena.domain.creatures import footprint_width
from srd_arena.domain.geometry import (
    Grid,
    GridDistance,
    Position,
    grid_distance_between,
)

from .encounter_models.actions import CreatureRef

if TYPE_CHECKING:
    from .encounter import EncounterState


def creature_position(state: EncounterState, creature_ref: CreatureRef) -> Position:
    """Return the anchor position of one runtime creature."""

    return state.creatures[creature_ref].position


def creature_size(state: EncounterState, creature_ref: CreatureRef) -> str:
    """Return the normalized size code stored by one runtime creature."""

    return state.creatures[creature_ref].creature.size


def occupied_cells(position: Position, size: str) -> tuple[Position, ...]:
    """Return every cell in the square footprint anchored at ``position``.

    Encounter positions identify the top-left cell of a footprint. Keeping that
    convention explicit lets content continue to use integer grid positions.

    >>> occupied_cells(Position(2, 3), "L")
    (Position(x=2, y=3), Position(x=3, y=3), Position(x=2, y=4), Position(x=3, y=4))
    """

    width = footprint_width(size)
    return tuple(
        Position(position.x + x_offset, position.y + y_offset)
        for y_offset in range(width)
        for x_offset in range(width)
    )


def creature_occupied_cells(
    state: EncounterState,
    creature_ref: CreatureRef,
    *,
    position: Position | None = None,
) -> tuple[Position, ...]:
    """Return a runtime creature's occupied cells at its current or proposed anchor.

    >>> from types import SimpleNamespace
    >>> creature_state = SimpleNamespace(
    ...     position=Position(1, 2), creature=SimpleNamespace(size="L")
    ... )
    >>> state = SimpleNamespace(creatures={"ogre": creature_state})
    >>> creature_occupied_cells(state, "ogre")[-1]
    Position(x=2, y=3)
    """

    creature_state = state.creatures[creature_ref]
    return occupied_cells(
        position or creature_state.position, creature_state.creature.size
    )


def minimum_cell_distance(
    source_cells: Iterable[Position],
    target_cells: Iterable[Position],
) -> GridDistance:
    """Return the shortest square-grid distance between two non-empty cell sets.

    >>> minimum_cell_distance(
    ...     (Position(0, 0), Position(1, 0)),
    ...     (Position(3, 0), Position(4, 0)),
    ... )
    2
    """

    source = tuple(source_cells)
    target = tuple(target_cells)
    if not source or not target:
        raise ValueError("Cannot measure distance from an empty footprint.")
    return GridDistance(
        min(grid_distance_between(a, b) for a in source for b in target)
    )


def creature_distance(
    state: EncounterState,
    source_ref: CreatureRef,
    target_ref: CreatureRef,
    *,
    source_position: Position | None = None,
    target_position: Position | None = None,
) -> GridDistance:
    """Return minimum distance between two creatures' occupied cells.

    Proposed anchors support movement and reaction checks without mutating state.
    """

    return minimum_cell_distance(
        creature_occupied_cells(state, source_ref, position=source_position),
        creature_occupied_cells(state, target_ref, position=target_position),
    )


def creatures_are_adjacent(
    state: EncounterState,
    source_ref: CreatureRef,
    target_ref: CreatureRef,
    *,
    source_position: Position | None = None,
    target_position: Position | None = None,
) -> bool:
    """Return whether any cells in two creature footprints are adjacent."""

    return (
        creature_distance(
            state,
            source_ref,
            target_ref,
            source_position=source_position,
            target_position=target_position,
        )
        == 1
    )


def footprint_is_within_grid(
    state: EncounterState,
    creature_ref: CreatureRef,
    position: Position,
) -> bool:
    """Return whether a proposed creature footprint lies wholly inside the grid."""

    grid = state.definition.grid
    return all(
        0 <= cell.x < grid.width and 0 <= cell.y < grid.height
        for cell in creature_occupied_cells(state, creature_ref, position=position)
    )


def placement_is_free(
    state: EncounterState,
    creature_ref: CreatureRef,
    position: Position,
    *,
    ignored_refs: Collection[CreatureRef] = (),
) -> bool:
    """Return whether a complete proposed footprint is in bounds and unoccupied.

    >>> from types import SimpleNamespace
    >>> grid = SimpleNamespace(width=5, height=5)
    >>> large = SimpleNamespace(
    ...     is_alive=True, position=Position(0, 0),
    ...     creature=SimpleNamespace(size="L"),
    ... )
    >>> blocker = SimpleNamespace(
    ...     is_alive=True, position=Position(3, 2),
    ...     creature=SimpleNamespace(size="M"),
    ... )
    >>> state = SimpleNamespace(
    ...     definition=SimpleNamespace(grid=grid),
    ...     creatures={"large": large, "blocker": blocker},
    ... )
    >>> placement_is_free(state, "large", Position(2, 1), ignored_refs={"large"})
    False
    >>> placement_is_free(state, "large", Position(4, 4), ignored_refs={"large"})
    False
    """

    proposed = creature_occupied_cells(state, creature_ref, position=position)
    if not footprint_is_within_grid(state, creature_ref, position):
        return False
    proposed_coordinates = {(cell.x, cell.y) for cell in proposed}
    for other_ref, other_state in state.creatures.items():
        if (
            other_ref == creature_ref
            or other_ref in ignored_refs
            or not other_state.is_alive
        ):
            continue
        if any(
            (cell.x, cell.y) in proposed_coordinates
            for cell in creature_occupied_cells(state, other_ref)
        ):
            return False
    return True


def creature_intersects_cells(
    state: EncounterState,
    creature_ref: CreatureRef,
    cells: Collection[tuple[int, int]],
) -> bool:
    """Return whether any occupied cell of a creature belongs to ``cells``."""

    return any(
        (cell.x, cell.y) in cells
        for cell in creature_occupied_cells(state, creature_ref)
    )


def validate_creature_placements(state: EncounterState) -> None:
    """Reject initial footprints that leave the grid or overlap another creature."""

    validate_placements(
        state.definition.grid,
        (
            (
                creature_ref,
                creature_position(state, creature_ref),
                creature_size(state, creature_ref),
            )
            for creature_ref in state.creatures
        ),
    )


def validate_placements(
    grid: Grid,
    placements: Iterable[tuple[CreatureRef, Position, str]],
) -> None:
    """Reject authored footprints that leave ``grid`` or overlap each other.

    This pure boundary is shared by content loading and runtime construction so
    invalid authored encounters fail early without weakening the runtime guard.
    """

    occupied_by: dict[tuple[int, int], CreatureRef] = {}
    for creature_ref, position, size in placements:
        cells = occupied_cells(position, size)
        if any(
            cell.x < 0 or cell.y < 0 or cell.x >= grid.width or cell.y >= grid.height
            for cell in cells
        ):
            raise ValueError(
                f"Creature '{creature_ref}' has a footprint outside the encounter grid."
            )
        for cell in cells:
            coordinate = (cell.x, cell.y)
            other_ref = occupied_by.get(coordinate)
            if other_ref is not None:
                raise ValueError(
                    f"Creature footprints for '{other_ref}' and '{creature_ref}' "
                    f"overlap at {coordinate}."
                )
            occupied_by[coordinate] = creature_ref
