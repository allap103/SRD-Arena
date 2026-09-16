"""Derive Burning Hands aim groups using only filtered, detached observations."""

from functools import lru_cache

from srd_arena.domain.encounters.rule_queries.obstructions import grid_ray_cells
from srd_arena.domain.encounters.spatial import occupied_cells
from srd_arena.domain.geometry import (
    Grid,
    Position,
    Vector2D,
    build_cone_area_from_vector,
)

from .area_observation_models import AreaAimObservation
from .filtered_observations import FilteredAction, FilteredObservation


def burning_hands_aims(
    observation: FilteredObservation, action: FilteredAction
) -> tuple[AreaAimObservation, ...] | None:
    """Group existing integer-coordinate aims by disclosed creature coverage.

    None means insufficient or unsupported information, not an empty area.
    Hidden and last-known rows cannot influence even the representative aim.
    Empty coverage is retained. These are geometric attempts, not legality probes.
    """
    template = action.cone_template
    if (
        action.spell is None
        or action.spell.spell_id != "burning_hands"
        or action.spell.area_shape != "cone"
        or template is None
    ):
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
    if actor is None or actor.position is None:
        return None
    if not (1 <= observation.grid.width <= 24 and 1 <= observation.grid.height <= 24):
        raise ValueError("Experimental aiming supports boards up to 24 by 24")
    origin = Position(actor.position.x, actor.position.y)
    blocked = {
        (c.position.x, c.position.y) for c in observation.terrain if c.cover == "total"
    }
    footprints = {
        c.creature_ref: frozenset(
            (p.x, p.y)
            for p in occupied_cells(Position(c.position.x, c.position.y), c.size)
        )
        for c in current
        if not c.defeated and c.position is not None and c.size is not None
    }
    # Total-cover filtering uses exactly the engine's ray traversal and excludes
    # the origin cell. Creature blockers provide partial cover, not area clipping.
    clear: dict[tuple[int, int], bool] = {}
    groups: dict[tuple[str, ...], AreaAimObservation] = {}
    for aim, cells in _cone_aim_cells(
        observation.grid.width,
        observation.grid.height,
        origin.x,
        origin.y,
        template.length_squares,
        template.coverage_threshold,
    ):
        for cell in cells:
            if cell not in clear:
                clear[cell] = not any(
                    (p.x, p.y) in blocked
                    for p in grid_ray_cells(origin, Position(*cell))[1:]
                )
        affected = frozenset(cell for cell in cells if clear[cell])
        refs = tuple(
            sorted(ref for ref, footprint in footprints.items() if footprint & affected)
        )
        groups.setdefault(refs, AreaAimObservation(aim, refs))
    return tuple(groups.values())


@lru_cache(maxsize=128)
def _cone_aim_cells(
    width: int,
    height: int,
    origin_x: int,
    origin_y: int,
    length: int,
    threshold: float,
) -> tuple[tuple[tuple[float, float], tuple[tuple[int, int], ...]], ...]:
    """Cache pure shapes, never creature state or visibility-dependent groups."""
    grid = Grid(width, height)
    origin = Position(origin_x, origin_y)
    result = []
    for y in range(height):
        for x in range(width):
            # Preserve the established command grammar (integer aim coordinates),
            # including the engine's half-cell caster-center offset.
            area = build_cone_area_from_vector(
                origin,
                Vector2D(x - (origin_x + 0.5), y - (origin_y + 0.5)),
                length,
                grid,
                coverage_threshold=threshold,
            )
            result.append(((float(x), float(y)), tuple((p.x, p.y) for p in area.cells)))
    return tuple(result)
