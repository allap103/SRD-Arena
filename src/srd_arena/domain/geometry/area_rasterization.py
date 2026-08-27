"""Polygon construction, clipping, and grid-cell rasterization."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .area_models import ContinuousArea, Point2D, Vector2D
from .area_vectors import (
    EPSILON,
    distance_squared,
    normalize_vector,
    perpendicular,
    translate,
)
from .primitives import Grid, Position

BOUNDARY_SHRINK = 1e-6


def continuous_area_outline(area: ContinuousArea) -> tuple[Point2D, ...] | None:
    if area.direction is None:
        return None
    direction = normalize_vector(area.direction)
    if area.shape == "cone" and area.length is not None:
        return cone_polygon(area.origin, direction, area.length)
    if area.shape == "line" and area.length is not None:
        return line_polygon(
            area.origin,
            direction,
            area.length,
            area.width or 1.0,
        )
    if area.shape == "cube" and area.length is not None:
        return cube_polygon(area.origin, direction, area.length)
    return None


def rasterize_cells(
    grid: Grid,
    includes_cell: Callable[[Position], bool],
) -> tuple[Position, ...]:
    return sorted_positions(
        Position(x, y)
        for y in range(grid.height)
        for x in range(grid.width)
        if includes_cell(Position(x, y))
    )


def sorted_positions(positions: Iterable[Position]) -> tuple[Position, ...]:
    return tuple(sorted(positions, key=lambda position: (position.y, position.x)))


def filter_origin_cell(
    origin: Position,
    cells: tuple[Position, ...],
) -> tuple[Position, ...]:
    return tuple(cell for cell in cells if cell.x != origin.x or cell.y != origin.y)


def cone_polygon(
    origin: Point2D,
    direction: Vector2D,
    length: float,
) -> tuple[Point2D, ...]:
    side = perpendicular(direction)
    far_center = translate(origin, direction, length)
    half_width = length / 2.0
    return (
        origin,
        translate(far_center, side, half_width),
        translate(far_center, side, -half_width),
    )


def line_polygon(
    origin: Point2D,
    direction: Vector2D,
    length: float,
    width: float = 1.0,
) -> tuple[Point2D, ...]:
    side = perpendicular(direction)
    end = translate(origin, direction, length)
    half_width = max((width / 2.0) - BOUNDARY_SHRINK, 0.0)
    return (
        translate(origin, side, half_width),
        translate(origin, side, -half_width),
        translate(end, side, -half_width),
        translate(end, side, half_width),
    )


def cube_polygon(
    origin: Point2D,
    direction: Vector2D,
    size: float,
) -> tuple[Point2D, ...]:
    side = perpendicular(direction)
    center = translate(origin, direction, (size / 2.0) + BOUNDARY_SHRINK)
    half_size = size / 2.0
    near_left = translate(translate(center, direction, -half_size), side, half_size)
    near_right = translate(translate(center, direction, -half_size), side, -half_size)
    far_right = translate(translate(center, direction, half_size), side, -half_size)
    far_left = translate(translate(center, direction, half_size), side, half_size)
    return (near_left, near_right, far_right, far_left)


def cell_intersects_circle(
    cell: Position,
    center: Point2D,
    radius: float,
) -> bool:
    min_x, max_x, min_y, max_y = cell_bounds(cell)
    closest_x = min(max(center.x, min_x), max_x)
    closest_y = min(max(center.y, min_y), max_y)
    return (
        distance_squared(center, Point2D(closest_x, closest_y))
        <= (radius * radius) + EPSILON
    )


def cell_meets_polygon_coverage_threshold(
    cell: Position,
    polygon: tuple[Point2D, ...],
    *,
    coverage_threshold: float,
) -> bool:
    return cell_polygon_overlap_area(cell, polygon) >= (coverage_threshold - EPSILON)


def cell_polygon_overlap_area(
    cell: Position,
    polygon: tuple[Point2D, ...],
) -> float:
    clipped = clip_polygon_to_cell(polygon, cell)
    if len(clipped) < 3:
        return 0.0
    return polygon_area(clipped)


def clip_polygon_to_cell(
    polygon: tuple[Point2D, ...],
    cell: Position,
) -> tuple[Point2D, ...]:
    min_x, max_x, min_y, max_y = cell_bounds(cell)
    clipped = list(polygon)
    clipped = _clip_polygon_against_boundary(
        clipped,
        inside=lambda point: point.x >= min_x - EPSILON,
        intersect=lambda start, end: _intersect_vertical(start, end, min_x),
    )
    clipped = _clip_polygon_against_boundary(
        clipped,
        inside=lambda point: point.x <= max_x + EPSILON,
        intersect=lambda start, end: _intersect_vertical(start, end, max_x),
    )
    clipped = _clip_polygon_against_boundary(
        clipped,
        inside=lambda point: point.y >= min_y - EPSILON,
        intersect=lambda start, end: _intersect_horizontal(start, end, min_y),
    )
    clipped = _clip_polygon_against_boundary(
        clipped,
        inside=lambda point: point.y <= max_y + EPSILON,
        intersect=lambda start, end: _intersect_horizontal(start, end, max_y),
    )
    return tuple(clipped)


def _clip_polygon_against_boundary(
    polygon: list[Point2D],
    *,
    inside: Callable[[Point2D], bool],
    intersect: Callable[[Point2D, Point2D], Point2D],
) -> list[Point2D]:
    if not polygon:
        return []
    clipped: list[Point2D] = []
    previous = polygon[-1]
    previous_inside = inside(previous)
    for current in polygon:
        current_inside = inside(current)
        if current_inside:
            if not previous_inside:
                clipped.append(intersect(previous, current))
            clipped.append(current)
        elif previous_inside:
            clipped.append(intersect(previous, current))
        previous = current
        previous_inside = current_inside
    return clipped


def _intersect_vertical(
    start: Point2D,
    end: Point2D,
    boundary_x: float,
) -> Point2D:
    delta_x = end.x - start.x
    if abs(delta_x) <= EPSILON:
        return Point2D(boundary_x, start.y)
    ratio = (boundary_x - start.x) / delta_x
    return Point2D(boundary_x, start.y + ((end.y - start.y) * ratio))


def _intersect_horizontal(
    start: Point2D,
    end: Point2D,
    boundary_y: float,
) -> Point2D:
    delta_y = end.y - start.y
    if abs(delta_y) <= EPSILON:
        return Point2D(start.x, boundary_y)
    ratio = (boundary_y - start.y) / delta_y
    return Point2D(start.x + ((end.x - start.x) * ratio), boundary_y)


def polygon_area(points: tuple[Point2D, ...]) -> float:
    signed_area = sum(
        (start.x * end.y) - (end.x * start.y) for start, end in polygon_edges(points)
    )
    return abs(signed_area) / 2.0


def polygon_edges(
    points: tuple[Point2D, ...],
) -> tuple[tuple[Point2D, Point2D], ...]:
    return tuple(
        (points[index], points[(index + 1) % len(points)])
        for index in range(len(points))
    )


def cell_bounds(cell: Position) -> tuple[float, float, float, float]:
    return (
        float(cell.x),
        float(cell.x + 1),
        float(cell.y),
        float(cell.y + 1),
    )
