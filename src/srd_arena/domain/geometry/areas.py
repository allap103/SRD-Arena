from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Iterable
import math

from .primitives import Grid, Position

DIRECTION_VECTORS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
    "up-left": (-1, -1),
    "up-right": (1, -1),
    "down-left": (-1, 1),
    "down-right": (1, 1),
}

RASTERIZATION_POLICY = "coverage_threshold"
LEGACY_TOUCHED_CELL_POLICY = "touched_cell"
EPSILON = 1e-9
BOUNDARY_SHRINK = 1e-6
DEFAULT_CELL_COVERAGE_THRESHOLD = 0.5


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class Vector2D:
    x: float
    y: float


@dataclass(frozen=True)
class ContinuousArea:
    shape: str
    origin: Point2D
    direction: Vector2D | None = None
    length: float | None = None
    width: float | None = None
    radius: float | None = None
    rasterization_policy: str = RASTERIZATION_POLICY
    coverage_threshold: float | None = None


@dataclass(frozen=True)
class AreaOfEffect:
    shape: str
    origin: Position
    cells: tuple[Position, ...]
    continuous_area: ContinuousArea | None = None
    rasterization_policy: str = RASTERIZATION_POLICY
    coverage_threshold: float | None = None


def serialize_area(area: AreaOfEffect | None) -> dict[str, object] | None:
    if area is None:
        return None
    payload: dict[str, object] = {
        "shape": area.shape,
        "origin": {"x": area.origin.x, "y": area.origin.y},
        "cells": [{"x": cell.x, "y": cell.y} for cell in area.cells],
        "rasterization_policy": area.rasterization_policy,
    }
    if area.coverage_threshold is not None:
        payload["coverage_threshold"] = area.coverage_threshold
    if area.continuous_area is not None:
        payload["continuous_area"] = serialize_continuous_area(area.continuous_area)
    return payload


def build_directional_area(
    shape: object,
    origin: Position,
    direction: Vector2D,
    size_squares: int,
    grid: Grid,
    *,
    coverage_threshold: float | None = None,
) -> AreaOfEffect | None:
    threshold = (
        DEFAULT_CELL_COVERAGE_THRESHOLD
        if coverage_threshold is None
        else coverage_threshold
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


def serialize_continuous_area(area: ContinuousArea) -> dict[str, object]:
    payload: dict[str, object] = {
        "shape": area.shape,
        "origin": {"x": area.origin.x, "y": area.origin.y},
        "rasterization_policy": area.rasterization_policy,
    }
    if area.direction is not None:
        payload["direction"] = {"x": area.direction.x, "y": area.direction.y}
    if area.length is not None:
        payload["length"] = area.length
    if area.width is not None:
        payload["width"] = area.width
    if area.radius is not None:
        payload["radius"] = area.radius
    if area.coverage_threshold is not None:
        payload["coverage_threshold"] = area.coverage_threshold
    return payload


def deserialize_continuous_area(payload: object) -> ContinuousArea | None:
    if not isinstance(payload, dict):
        return None
    shape = payload.get("shape")
    origin = payload.get("origin")
    if (
        not isinstance(shape, str)
        or not isinstance(origin, dict)
        or not isinstance(origin.get("x"), (int, float))
        or not isinstance(origin.get("y"), (int, float))
    ):
        return None
    direction_payload = payload.get("direction")
    direction = None
    if (
        isinstance(direction_payload, dict)
        and isinstance(direction_payload.get("x"), (int, float))
        and isinstance(direction_payload.get("y"), (int, float))
    ):
        direction = Vector2D(
            float(direction_payload["x"]),
            float(direction_payload["y"]),
        )
    return ContinuousArea(
        shape=shape,
        origin=Point2D(float(origin["x"]), float(origin["y"])),
        direction=direction,
        length=float(payload["length"])
        if isinstance(payload.get("length"), (int, float))
        else None,
        width=float(payload["width"])
        if isinstance(payload.get("width"), (int, float))
        else None,
        radius=float(payload["radius"])
        if isinstance(payload.get("radius"), (int, float))
        else None,
        rasterization_policy=(
            str(payload["rasterization_policy"])
            if isinstance(payload.get("rasterization_policy"), str)
            else RASTERIZATION_POLICY
        ),
        coverage_threshold=(
            float(payload["coverage_threshold"])
            if isinstance(payload.get("coverage_threshold"), (int, float))
            else None
        ),
    )


def continuous_area_outline(area: ContinuousArea) -> tuple[Point2D, ...] | None:
    if area.direction is None:
        return None
    if area.shape == "cone" and area.length is not None:
        return _cone_polygon(area.origin, normalize_vector(area.direction), area.length)
    if area.shape == "line" and area.length is not None:
        return _line_polygon(area.origin, normalize_vector(area.direction), area.length)
    if area.shape == "cube" and area.length is not None:
        return _cube_polygon(area.origin, normalize_vector(area.direction), area.length)
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
        rasterization_policy=LEGACY_TOUCHED_CELL_POLICY,
    )
    cells = _rasterize_cells(
        grid,
        lambda cell: _cell_intersects_circle(cell, origin_point, float(radius_squares)),
    )
    return AreaOfEffect(
        shape="radius",
        origin=origin,
        cells=cells,
        continuous_area=continuous_area,
        rasterization_policy=LEGACY_TOUCHED_CELL_POLICY,
    )


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
    polygon = _cone_polygon(
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
    cells = _filter_origin_cell(
        origin,
        _rasterize_cells(
            grid,
            lambda cell: _cell_meets_polygon_coverage_threshold(
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
) -> AreaOfEffect:
    return build_line_area_from_vector(
        origin,
        vector_from_direction(direction),
        length_squares,
        grid,
    )


def build_line_area_from_vector(
    origin: Position,
    direction: Vector2D,
    length_squares: int,
    grid: Grid,
    *,
    coverage_threshold: float = DEFAULT_CELL_COVERAGE_THRESHOLD,
) -> AreaOfEffect:
    unit_direction = normalize_vector(direction)
    origin_point = directional_origin_point(origin, unit_direction)
    polygon = _line_polygon(
        origin_point,
        unit_direction,
        max(float(length_squares) - BOUNDARY_SHRINK, 0.0),
    )
    continuous_area = ContinuousArea(
        shape="line",
        origin=origin_point,
        direction=unit_direction,
        length=float(length_squares),
        width=1.0,
        coverage_threshold=coverage_threshold,
    )
    cells = _filter_origin_cell(
        origin,
        _rasterize_cells(
            grid,
            lambda cell: _cell_meets_polygon_coverage_threshold(
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
    polygon = _cube_polygon(
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
    cells = _filter_origin_cell(
        origin,
        _rasterize_cells(
            grid,
            lambda cell: _cell_meets_polygon_coverage_threshold(
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


def point_from_position(position: Position) -> Point2D:
    return Point2D(float(position.x) + 0.5, float(position.y) + 0.5)


def directional_origin_point(origin: Position, direction: Vector2D) -> Point2D:
    center = point_from_position(origin)
    return _translate(center, direction, 0.5)


def vector_from_direction(direction: str) -> Vector2D:
    if direction not in DIRECTION_VECTORS:
        raise ValueError(f"Unsupported direction: {direction!r}.")
    dx, dy = DIRECTION_VECTORS[direction]
    return normalize_vector(Vector2D(float(dx), float(dy)))


def vector_between_positions(origin: Position, target: Position) -> Vector2D:
    dx = float(target.x - origin.x)
    dy = float(target.y - origin.y)
    return normalize_vector(Vector2D(dx, dy))


def normalize_vector(vector: Vector2D) -> Vector2D:
    magnitude = math.hypot(vector.x, vector.y)
    if magnitude <= EPSILON:
        raise ValueError("Direction vector must be non-zero.")
    return Vector2D(vector.x / magnitude, vector.y / magnitude)


def _rasterize_cells(
    grid: Grid,
    includes_cell: Callable[[Position], bool],
) -> tuple[Position, ...]:
    return _sorted_positions(
        Position(x, y)
        for y in range(grid.height)
        for x in range(grid.width)
        if includes_cell(Position(x, y))
    )


def _sorted_positions(positions: Iterable[Position]) -> tuple[Position, ...]:
    return tuple(sorted(positions, key=lambda position: (position.y, position.x)))


def _filter_origin_cell(
    origin: Position,
    cells: tuple[Position, ...],
) -> tuple[Position, ...]:
    return tuple(cell for cell in cells if cell.x != origin.x or cell.y != origin.y)


def _cone_polygon(
    origin: Point2D,
    direction: Vector2D,
    length: float,
) -> tuple[Point2D, ...]:
    perpendicular = _perpendicular(direction)
    far_center = _translate(origin, direction, length)
    half_width = length / 2.0
    return (
        origin,
        _translate(far_center, perpendicular, half_width),
        _translate(far_center, perpendicular, -half_width),
    )


def _line_polygon(
    origin: Point2D,
    direction: Vector2D,
    length: float,
) -> tuple[Point2D, ...]:
    perpendicular = _perpendicular(direction)
    end = _translate(origin, direction, length)
    half_width = 0.5 - BOUNDARY_SHRINK
    return (
        _translate(origin, perpendicular, half_width),
        _translate(origin, perpendicular, -half_width),
        _translate(end, perpendicular, -half_width),
        _translate(end, perpendicular, half_width),
    )


def _cube_polygon(
    origin: Point2D,
    direction: Vector2D,
    size: float,
) -> tuple[Point2D, ...]:
    perpendicular = _perpendicular(direction)
    center = _translate(origin, direction, (size / 2.0) + BOUNDARY_SHRINK)
    half_size = size / 2.0
    near_left = _translate(
        _translate(center, direction, -half_size), perpendicular, half_size
    )
    near_right = _translate(
        _translate(center, direction, -half_size), perpendicular, -half_size
    )
    far_right = _translate(
        _translate(center, direction, half_size), perpendicular, -half_size
    )
    far_left = _translate(
        _translate(center, direction, half_size), perpendicular, half_size
    )
    return (near_left, near_right, far_right, far_left)


def _translate(point: Point2D, direction: Vector2D, distance: float) -> Point2D:
    return Point2D(
        point.x + (direction.x * distance),
        point.y + (direction.y * distance),
    )


def _perpendicular(direction: Vector2D) -> Vector2D:
    return Vector2D(-direction.y, direction.x)


def _cell_intersects_circle(
    cell: Position,
    center: Point2D,
    radius: float,
) -> bool:
    min_x, max_x, min_y, max_y = _cell_bounds(cell)
    closest_x = min(max(center.x, min_x), max_x)
    closest_y = min(max(center.y, min_y), max_y)
    return (
        _distance_squared(center, Point2D(closest_x, closest_y))
        <= (radius * radius) + EPSILON
    )


def _cell_meets_polygon_coverage_threshold(
    cell: Position,
    polygon: tuple[Point2D, ...],
    *,
    coverage_threshold: float,
) -> bool:
    return _cell_polygon_overlap_area(cell, polygon) >= (coverage_threshold - EPSILON)


def _cell_polygon_overlap_area(
    cell: Position,
    polygon: tuple[Point2D, ...],
) -> float:
    clipped = _clip_polygon_to_cell(polygon, cell)
    if len(clipped) < 3:
        return 0.0
    return _polygon_area(clipped)


def _clip_polygon_to_cell(
    polygon: tuple[Point2D, ...],
    cell: Position,
) -> tuple[Point2D, ...]:
    min_x, max_x, min_y, max_y = _cell_bounds(cell)
    clipped = list(polygon)
    clipped = _clip_polygon_against_boundary(
        clipped,
        inside=lambda point: point.x >= min_x - EPSILON,
        intersect=lambda start, end: _intersect_with_vertical_boundary(
            start, end, min_x
        ),
    )
    clipped = _clip_polygon_against_boundary(
        clipped,
        inside=lambda point: point.x <= max_x + EPSILON,
        intersect=lambda start, end: _intersect_with_vertical_boundary(
            start, end, max_x
        ),
    )
    clipped = _clip_polygon_against_boundary(
        clipped,
        inside=lambda point: point.y >= min_y - EPSILON,
        intersect=lambda start, end: _intersect_with_horizontal_boundary(
            start, end, min_y
        ),
    )
    clipped = _clip_polygon_against_boundary(
        clipped,
        inside=lambda point: point.y <= max_y + EPSILON,
        intersect=lambda start, end: _intersect_with_horizontal_boundary(
            start, end, max_y
        ),
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


def _intersect_with_vertical_boundary(
    start: Point2D,
    end: Point2D,
    boundary_x: float,
) -> Point2D:
    delta_x = end.x - start.x
    if abs(delta_x) <= EPSILON:
        return Point2D(boundary_x, start.y)
    ratio = (boundary_x - start.x) / delta_x
    return Point2D(boundary_x, start.y + ((end.y - start.y) * ratio))


def _intersect_with_horizontal_boundary(
    start: Point2D,
    end: Point2D,
    boundary_y: float,
) -> Point2D:
    delta_y = end.y - start.y
    if abs(delta_y) <= EPSILON:
        return Point2D(start.x, boundary_y)
    ratio = (boundary_y - start.y) / delta_y
    return Point2D(start.x + ((end.x - start.x) * ratio), boundary_y)


def _polygon_area(points: tuple[Point2D, ...]) -> float:
    signed_area = 0.0
    for start, end in _polygon_edges(points):
        signed_area += (start.x * end.y) - (end.x * start.y)
    return abs(signed_area) / 2.0


def _cell_intersects_polygon(
    cell: Position,
    polygon: tuple[Point2D, ...],
) -> bool:
    corners = _cell_corners(cell)
    axes = [
        Vector2D(1.0, 0.0),
        Vector2D(0.0, 1.0),
        *(
            normalize_vector(Vector2D(-(end.y - start.y), end.x - start.x))
            for start, end in _polygon_edges(polygon)
            if _distance_squared(start, end) > EPSILON
        ),
    ]
    return all(
        _intervals_overlap(
            _project_points(corners, axis),
            _project_points(polygon, axis),
        )
        for axis in axes
    )


def _cell_bounds(cell: Position) -> tuple[float, float, float, float]:
    return (
        float(cell.x),
        float(cell.x + 1),
        float(cell.y),
        float(cell.y + 1),
    )


def _cell_corners(cell: Position) -> tuple[Point2D, ...]:
    min_x, max_x, min_y, max_y = _cell_bounds(cell)
    return (
        Point2D(min_x, min_y),
        Point2D(max_x, min_y),
        Point2D(max_x, max_y),
        Point2D(min_x, max_y),
    )


def _polygon_edges(points: tuple[Point2D, ...]) -> tuple[tuple[Point2D, Point2D], ...]:
    return tuple(
        (points[index], points[(index + 1) % len(points)])
        for index in range(len(points))
    )


def _project_points(
    points: tuple[Point2D, ...],
    axis: Vector2D,
) -> tuple[float, float]:
    values = tuple((point.x * axis.x) + (point.y * axis.y) for point in points)
    return min(values), max(values)


def _intervals_overlap(
    interval_a: tuple[float, float],
    interval_b: tuple[float, float],
) -> bool:
    overlap = min(interval_a[1], interval_b[1]) - max(interval_a[0], interval_b[0])
    return overlap > EPSILON


def _distance_squared(point_a: Point2D, point_b: Point2D) -> float:
    delta_x = point_a.x - point_b.x
    delta_y = point_a.y - point_b.y
    return (delta_x * delta_x) + (delta_y * delta_y)
