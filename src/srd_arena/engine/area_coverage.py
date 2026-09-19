"""Derive per-aim area coverage using only filtered, detached observations."""

from functools import lru_cache

from srd_arena.domain.encounters.rule_queries.obstructions import grid_ray_cells
from srd_arena.domain.encounters.spatial import occupied_cells
from srd_arena.domain.geometry import (
    AreaOfEffect,
    Grid,
    Position,
    Vector2D,
    build_directional_area,
    build_point_cube_area,
    build_radius_area,
)

from .area_observation_models import AreaAimObservation, AreaTemplateObservation
from .filtered_observations import FilteredAction, FilteredObservation


def area_aims(
    observation: FilteredObservation, action: FilteredAction
) -> tuple[AreaAimObservation, ...] | None:
    """Annotate every integer aim with disclosed living creature coverage.

    None means insufficient or unsupported information, not an empty area.
    Hidden and last-known rows cannot influence coverage. No aim is removed.
    These are geometric attempts, not legality probes or predicted outcomes.
    """
    template = action.area_template
    if template is None:
        return None
    current = [
        c
        for c in observation.creatures
        if c.knowledge == "current"
        and (c.currently_visible or c.allegiance in {"own", "ally"})
    ]
    if any(c.position is None or c.size is None or c.defeated is None for c in current):
        return None
    actor = next((c for c in current if c.creature_ref == action.creature_ref), None)
    if template.placement == "directional" and (
        actor is None or actor.position is None
    ):
        return None
    if not (1 <= observation.grid.width <= 24 and 1 <= observation.grid.height <= 24):
        raise ValueError("Experimental aiming supports boards up to 24 by 24")
    # Point-area geometry is independent of the caster's position.
    anchor = (
        (actor.position.x, actor.position.y)
        if template.placement == "directional" and actor and actor.position
        else (0, 0)
    )
    blocked = frozenset(
        (c.position.x, c.position.y) for c in observation.terrain if c.cover == "total"
    )
    footprints = {
        c.creature_ref: frozenset(
            (p.x, p.y)
            for p in occupied_cells(Position(c.position.x, c.position.y), c.size)
        )
        for c in current
        if not c.defeated and c.position is not None and c.size is not None
    }
    result = []
    for aim, origin, cells in _area_aim_cells(
        observation.grid.width, observation.grid.height, *anchor, template
    ):
        affected = frozenset(
            cell for cell in cells if _clear_ray(origin, cell, blocked)
        )
        refs = tuple(
            sorted(ref for ref, footprint in footprints.items() if footprint & affected)
        )
        result.append(AreaAimObservation(aim, refs))
    return tuple(result)


@lru_cache(maxsize=32768)
def _clear_ray(
    origin: tuple[int, int],
    cell: tuple[int, int],
    blocked: frozenset[tuple[int, int]],
) -> bool:
    """Cache public terrain geometry, excluding the effect's origin cell."""
    return not blocked or not any(
        (p.x, p.y) in blocked
        for p in grid_ray_cells(Position(*origin), Position(*cell))[1:]
    )


@lru_cache(maxsize=128)
def _area_aim_cells(
    width: int,
    height: int,
    origin_x: int,
    origin_y: int,
    template: AreaTemplateObservation,
) -> tuple[
    tuple[tuple[float, float], tuple[int, int], tuple[tuple[int, int], ...]], ...
]:
    """Cache pure shapes, never creature state or visibility-dependent coverage."""
    grid = Grid(width, height)
    result = []
    for y in range(height):
        for x in range(width):
            area: AreaOfEffect | None
            if template.placement == "point":
                origin = Position(x, y)
                if template.shape == "cube":
                    area = build_point_cube_area(origin, template.size_squares, grid)
                elif template.shape == "radius":
                    area = build_radius_area(origin, template.size_squares, grid)
                else:
                    raise ValueError(f"Unsupported point area: {template.shape}")
            else:
                origin = Position(origin_x, origin_y)
                # Match the runtime's half-cell caster-center offset.
                area = build_directional_area(
                    template.shape,
                    origin,
                    Vector2D(x - (origin_x + 0.5), y - (origin_y + 0.5)),
                    template.size_squares,
                    grid,
                    width_squares=template.width_squares,
                    coverage_threshold=template.coverage_threshold,
                )
                if area is None:
                    raise ValueError(f"Unsupported directional area: {template.shape}")
            result.append(
                (
                    (float(x), float(y)),
                    (origin.x, origin.y),
                    tuple((p.x, p.y) for p in area.cells),
                )
            )
    return tuple(result)
