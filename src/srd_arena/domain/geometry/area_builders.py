"""Construct continuous templates and rasterize them onto a grid."""

from __future__ import annotations

from .area_models import (
    DEFAULT_CELL_COVERAGE_THRESHOLD,
    TOUCHED_CELL_POLICY,
    AreaOfEffect,
    ContinuousArea,
    Vector2D,
)
from .area_rasterization import (
    BOUNDARY_SHRINK,
    cell_intersects_circle,
    cell_meets_polygon_coverage_threshold,
    cone_polygon,
    cube_polygon,
    filter_origin_cell,
    line_polygon,
    rasterize_cells,
)
from .area_vectors import (
    directional_origin_point,
    normalize_vector,
    point_from_position,
    vector_from_direction,
)
from .primitives import Grid, Position


def build_directional_area(
    shape: object,
    origin: Position,
    direction: Vector2D,
    size_squares: int,
    grid: Grid,
    *,
    width_squares: float | None = None,
    coverage_threshold: float | None = None,
) -> AreaOfEffect | None:
    threshold = (
        coverage_threshold
        if coverage_threshold is not None
        else DEFAULT_CELL_COVERAGE_THRESHOLD
    )
    if shape == "cone":
        return build_cone_area_from_vector(
            origin,
            direction,
            size_squares,
            grid,
            coverage_threshold=threshold,
        )
    if shape == "line":
        return build_line_area_from_vector(
            origin,
            direction,
            size_squares,
            grid,
            width_squares=width_squares or 1.0,
            coverage_threshold=threshold,
        )
    if shape == "cube":
        return build_cube_area_from_vector(
            origin,
            direction,
            size_squares,
            grid,
            coverage_threshold=threshold,
        )
    return None


def build_radius_area(
    origin: Position,
    radius_squares: int,
    grid: Grid,
) -> AreaOfEffect:
    origin_point = point_from_position(origin)
    continuous_area = ContinuousArea(
        shape="radius",
        origin=origin_point,
        radius=float(radius_squares),
        rasterization_policy=TOUCHED_CELL_POLICY,
    )
    cells = rasterize_cells(
        grid,
        lambda cell: cell_intersects_circle(
            cell,
            origin_point,
            float(radius_squares),
        ),
    )
    return AreaOfEffect(
        shape="radius",
        origin=origin,
        cells=cells,
        continuous_area=continuous_area,
        rasterization_policy=TOUCHED_CELL_POLICY,
    )


def build_point_cube_area(
    origin: Position,
    size_squares: int,
    grid: Grid,
) -> AreaOfEffect:
    """Build a grid-aligned cube centered on a selected battlefield cell."""
    start_x = origin.x - ((size_squares - 1) // 2)
    start_y = origin.y - ((size_squares - 1) // 2)
    cells = tuple(
        Position(x, y)
        for y in range(start_y, start_y + size_squares)
        for x in range(start_x, start_x + size_squares)
        if 0 <= x < grid.width and 0 <= y < grid.height
    )
    return AreaOfEffect(shape="cube", origin=origin, cells=cells)


def build_cone_area(
    origin: Position,
    direction: str,
    length_squares: int,
    grid: Grid,
) -> AreaOfEffect:
    return build_cone_area_from_vector(
        origin,
        vector_from_direction(direction),
        length_squares,
        grid,
    )


def build_cone_area_from_vector(
    origin: Position,
    direction: Vector2D,
    length_squares: int,
    grid: Grid,
    *,
    coverage_threshold: float = DEFAULT_CELL_COVERAGE_THRESHOLD,
) -> AreaOfEffect:
    unit_direction = normalize_vector(direction)
    origin_point = directional_origin_point(origin, unit_direction)
    polygon = cone_polygon(
        origin_point,
        unit_direction,
        max(float(length_squares) - BOUNDARY_SHRINK, 0.0),
    )
    continuous_area = ContinuousArea(
        shape="cone",
        origin=origin_point,
        direction=unit_direction,
        length=float(length_squares),
        coverage_threshold=coverage_threshold,
    )
    cells = filter_origin_cell(
        origin,
        rasterize_cells(
            grid,
            lambda cell: cell_meets_polygon_coverage_threshold(
                cell,
                polygon,
                coverage_threshold=coverage_threshold,
            ),
        ),
    )
    return AreaOfEffect(
        shape="cone",
        origin=origin,
        cells=cells,
        continuous_area=continuous_area,
        coverage_threshold=coverage_threshold,
    )


def build_line_area(
    origin: Position,
    direction: str,
    length_squares: int,
    grid: Grid,
    *,
    width_squares: float = 1.0,
    coverage_threshold: float = DEFAULT_CELL_COVERAGE_THRESHOLD,
) -> AreaOfEffect:
    return build_line_area_from_vector(
        origin,
        vector_from_direction(direction),
        length_squares,
        grid,
        width_squares=width_squares,
        coverage_threshold=coverage_threshold,
    )


def build_line_area_from_vector(
    origin: Position,
    direction: Vector2D,
    length_squares: int,
    grid: Grid,
    *,
    width_squares: float = 1.0,
    coverage_threshold: float = DEFAULT_CELL_COVERAGE_THRESHOLD,
) -> AreaOfEffect:
    unit_direction = normalize_vector(direction)
    origin_point = directional_origin_point(origin, unit_direction)
    polygon = line_polygon(
        origin_point,
        unit_direction,
        max(float(length_squares) - BOUNDARY_SHRINK, 0.0),
        width_squares,
    )
    continuous_area = ContinuousArea(
        shape="line",
        origin=origin_point,
        direction=unit_direction,
        length=float(length_squares),
        width=width_squares,
        coverage_threshold=coverage_threshold,
    )
    cells = filter_origin_cell(
        origin,
        rasterize_cells(
            grid,
            lambda cell: cell_meets_polygon_coverage_threshold(
                cell,
                polygon,
                coverage_threshold=coverage_threshold,
            ),
        ),
    )
    return AreaOfEffect(
        shape="line",
        origin=origin,
        cells=cells,
        continuous_area=continuous_area,
        coverage_threshold=coverage_threshold,
    )


def build_cube_area(
    origin: Position,
    direction: str,
    size_squares: int,
    grid: Grid,
) -> AreaOfEffect:
    return build_cube_area_from_vector(
        origin,
        vector_from_direction(direction),
        size_squares,
        grid,
    )


def build_cube_area_from_vector(
    origin: Position,
    direction: Vector2D,
    size_squares: int,
    grid: Grid,
    *,
    coverage_threshold: float = DEFAULT_CELL_COVERAGE_THRESHOLD,
) -> AreaOfEffect:
    unit_direction = normalize_vector(direction)
    origin_point = directional_origin_point(origin, unit_direction)
    polygon = cube_polygon(
        origin_point,
        unit_direction,
        max(float(size_squares) - BOUNDARY_SHRINK, 0.0),
    )
    continuous_area = ContinuousArea(
        shape="cube",
        origin=origin_point,
        direction=unit_direction,
        length=float(size_squares),
        width=float(size_squares),
        coverage_threshold=coverage_threshold,
    )
    cells = filter_origin_cell(
        origin,
        rasterize_cells(
            grid,
            lambda cell: cell_meets_polygon_coverage_threshold(
                cell,
                polygon,
                coverage_threshold=coverage_threshold,
            ),
        ),
    )
    return AreaOfEffect(
        shape="cube",
        origin=origin,
        cells=cells,
        continuous_area=continuous_area,
        coverage_threshold=coverage_threshold,
    )
