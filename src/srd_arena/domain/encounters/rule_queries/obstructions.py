"""Answer cover and line-of-effect questions on the ground grid."""

from __future__ import annotations

from dataclasses import dataclass

from srd_arena.domain.geometry import Position

from ..encounter_models.actions import CreatureRef
from ..spatial import SpatialContext, creature_occupied_cells, terrain_at
from ..terrain import CoverDegree


@dataclass(frozen=True)
class CoverResult:
    """Report the least obstructed ray between two battlefield footprints."""

    degree: CoverDegree = CoverDegree.NONE
    terrain_cells: tuple[Position, ...] = ()
    creature_refs: tuple[CreatureRef, ...] = ()

    @property
    def bonus(self) -> int:
        """Return the Armor Class and Dexterity-save bonus from this cover."""

        return self.degree.bonus

    @property
    def has_line_of_effect(self) -> bool:
        """Return whether the target is not wholly behind Total Cover."""

        return self.degree is not CoverDegree.TOTAL


def grid_ray_cells(start: Position, end: Position) -> tuple[Position, ...]:
    """Rasterize the center-to-center grid ray between two cells.

    The deterministic integer traversal includes both endpoints and treats an
    exact diagonal as crossing diagonal cells rather than both touching cells.

    >>> grid_ray_cells(Position(0, 0), Position(3, 1))
    (Position(x=0, y=0), Position(x=1, y=0), Position(x=2, y=1), Position(x=3, y=1))
    """

    x, y = start.x, start.y
    delta_x = end.x - start.x
    delta_y = end.y - start.y
    horizontal_steps = abs(delta_x)
    vertical_steps = abs(delta_y)
    x_direction = 0 if delta_x == 0 else (1 if delta_x > 0 else -1)
    y_direction = 0 if delta_y == 0 else (1 if delta_y > 0 else -1)
    horizontal_index = 0
    vertical_index = 0
    cells = [Position(x, y)]
    while horizontal_index < horizontal_steps or vertical_index < vertical_steps:
        decision = (1 + (2 * horizontal_index)) * vertical_steps - (
            1 + (2 * vertical_index)
        ) * horizontal_steps
        if decision == 0:
            x += x_direction
            y += y_direction
            horizontal_index += 1
            vertical_index += 1
        elif decision < 0:
            x += x_direction
            horizontal_index += 1
        else:
            y += y_direction
            vertical_index += 1
        cells.append(Position(x, y))
    return tuple(cells)


def cover_between(
    state: SpatialContext,
    source_ref: CreatureRef,
    target_ref: CreatureRef,
) -> CoverResult:
    """Return cover on the least obstructed ray between two footprints.

    Terrain contributes its authored cover degree. Any third living creature
    intersecting a ray contributes Half Cover. Multi-cell creatures use the
    least protected source-to-target cell pair, representing an attacker using
    its clearest available angle.
    """

    source_cells = creature_occupied_cells(state, source_ref)
    target_cells = creature_occupied_cells(state, target_ref)
    results = tuple(
        _cover_on_ray(state, source_ref, target_ref, source, target)
        for source in source_cells
        for target in target_cells
    )
    return min(results, key=lambda result: result.degree.rank)


def cover_from_position(
    state: SpatialContext,
    source: Position,
    target_ref: CreatureRef,
    *,
    source_ref: CreatureRef | None = None,
) -> CoverResult:
    """Return cover on the clearest ray from one effect origin to a footprint."""

    results = tuple(
        _cover_on_ray(state, source_ref, target_ref, source, target)
        for target in creature_occupied_cells(state, target_ref)
    )
    return min(results, key=lambda result: result.degree.rank)


def cell_has_line_of_effect(
    state: SpatialContext,
    source: Position,
    target: Position,
) -> bool:
    """Return whether Total Cover terrain does not block a cell from an origin."""

    return not any(
        terrain is not None and terrain.cover is CoverDegree.TOTAL
        for cell in grid_ray_cells(source, target)[1:]
        if (terrain := terrain_at(state, cell)) is not None
    )


def cells_with_line_of_effect(
    state: SpatialContext,
    source: Position,
    targets: tuple[Position, ...],
) -> tuple[Position, ...]:
    """Filter target cells to those reachable from an effect origin."""

    return tuple(
        target for target in targets if cell_has_line_of_effect(state, source, target)
    )


def creature_has_line_of_effect_to_cell(
    state: SpatialContext,
    source_ref: CreatureRef,
    target: Position,
) -> bool:
    """Return whether any occupied source cell has an unblocked ray to a cell."""

    return any(
        cell_has_line_of_effect(state, source, target)
        for source in creature_occupied_cells(state, source_ref)
    )


def _cover_on_ray(
    state: SpatialContext,
    source_ref: CreatureRef | None,
    target_ref: CreatureRef,
    source: Position,
    target: Position,
) -> CoverResult:
    intervening = grid_ray_cells(source, target)[1:-1]
    terrain_degrees: list[tuple[Position, CoverDegree]] = []
    for cell in intervening:
        terrain = terrain_at(state, cell)
        if terrain is not None and terrain.cover is not CoverDegree.NONE:
            terrain_degrees.append((cell, terrain.cover))
    creature_refs = tuple(
        creature_ref
        for creature_ref, creature_state in state.creatures.items()
        if creature_ref not in {source_ref, target_ref}
        and creature_state.is_alive
        and any(
            cell in intervening for cell in creature_occupied_cells(state, creature_ref)
        )
    )
    degree = max(
        (
            *(cover for _, cover in terrain_degrees),
            *(CoverDegree.HALF for _ in creature_refs),
            CoverDegree.NONE,
        ),
        key=lambda cover: cover.rank,
    )
    return CoverResult(
        degree,
        tuple(cell for cell, cover in terrain_degrees if cover is degree),
        creature_refs if degree is CoverDegree.HALF else (),
    )
