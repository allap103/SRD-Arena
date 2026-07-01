from __future__ import annotations

from dataclasses import dataclass

from .models.scene import Grid, Position

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


@dataclass(frozen=True)
class AreaOfEffect:
    shape: str
    origin: Position
    cells: tuple[Position, ...]


def serialize_area(area: AreaOfEffect | None) -> dict[str, object] | None:
    if area is None:
        return None
    return {
        "shape": area.shape,
        "origin": {"x": area.origin.x, "y": area.origin.y},
        "cells": [{"x": cell.x, "y": cell.y} for cell in area.cells],
    }


def build_radius_area(
    origin: Position,
    radius_squares: int,
    grid: Grid,
) -> AreaOfEffect:
    cells = _sorted_positions(
        Position(x, y)
        for y in range(grid.height)
        for x in range(grid.width)
        if max(abs(x - origin.x), abs(y - origin.y)) <= radius_squares
    )
    return AreaOfEffect(shape="radius", origin=origin, cells=cells)


def build_cone_area(
    origin: Position,
    direction: str,
    length_squares: int,
    grid: Grid,
) -> AreaOfEffect:
    if direction not in DIRECTION_VECTORS:
        raise ValueError(f"Unsupported cone direction: {direction!r}.")
    dx, dy = DIRECTION_VECTORS[direction]
    cells = _sorted_positions(
        Position(x, y)
        for y in range(grid.height)
        for x in range(grid.width)
        if _is_in_cone(
            target=Position(x, y),
            origin=origin,
            direction_x=dx,
            direction_y=dy,
            length_squares=length_squares,
        )
    )
    return AreaOfEffect(shape="cone", origin=origin, cells=cells)


def build_line_area(
    origin: Position,
    direction: str,
    length_squares: int,
    grid: Grid,
) -> AreaOfEffect:
    if direction not in DIRECTION_VECTORS:
        raise ValueError(f"Unsupported line direction: {direction!r}.")
    dx, dy = DIRECTION_VECTORS[direction]
    cells = _sorted_positions(
        Position(origin.x + (dx * step), origin.y + (dy * step))
        for step in range(1, length_squares + 1)
        if _is_within_grid(
            origin.x + (dx * step),
            origin.y + (dy * step),
            grid,
        )
    )
    return AreaOfEffect(shape="line", origin=origin, cells=cells)


def build_cube_area(
    origin: Position,
    direction: str,
    size_squares: int,
    grid: Grid,
) -> AreaOfEffect:
    if direction not in DIRECTION_VECTORS:
        raise ValueError(f"Unsupported cube direction: {direction!r}.")
    dx, dy = DIRECTION_VECTORS[direction]
    cells = _sorted_positions(
        Position(x, y)
        for y in range(grid.height)
        for x in range(grid.width)
        if _is_in_cube(
            target=Position(x, y),
            origin=origin,
            direction_x=dx,
            direction_y=dy,
            size_squares=size_squares,
        )
    )
    return AreaOfEffect(shape="cube", origin=origin, cells=cells)


def _sorted_positions(positions) -> tuple[Position, ...]:
    return tuple(sorted(positions, key=lambda position: (position.y, position.x)))


def _is_within_grid(x: int, y: int, grid: Grid) -> bool:
    return 0 <= x < grid.width and 0 <= y < grid.height


def _is_in_cone(
    *,
    target: Position,
    origin: Position,
    direction_x: int,
    direction_y: int,
    length_squares: int,
) -> bool:
    offset_x = target.x - origin.x
    offset_y = target.y - origin.y
    if offset_x == 0 and offset_y == 0:
        return False

    if direction_x == 0:
        forward = -offset_y if direction_y < 0 else offset_y
        lateral = abs(offset_x)
    elif direction_y == 0:
        forward = -offset_x if direction_x < 0 else offset_x
        lateral = abs(offset_y)
    else:
        aligned_x = offset_x * direction_x
        aligned_y = offset_y * direction_y
        if aligned_x <= 0 or aligned_y <= 0:
            return False
        forward = max(aligned_x, aligned_y)
        lateral = abs(aligned_x - aligned_y)

    return 1 <= forward <= length_squares and lateral <= forward - 1


def _is_in_cube(
    *,
    target: Position,
    origin: Position,
    direction_x: int,
    direction_y: int,
    size_squares: int,
) -> bool:
    offset_x = target.x - origin.x
    offset_y = target.y - origin.y
    if offset_x == 0 and offset_y == 0:
        return False

    min_x, max_x = _axis_range(offset_x, direction_x, size_squares)
    min_y, max_y = _axis_range(offset_y, direction_y, size_squares)
    return min_x <= offset_x <= max_x and min_y <= offset_y <= max_y


def _axis_range(offset: int, direction: int, size_squares: int) -> tuple[int, int]:
    if direction > 0:
        return 1, size_squares
    if direction < 0:
        return -size_squares, -1

    half_span = size_squares // 2
    return -half_span, half_span
