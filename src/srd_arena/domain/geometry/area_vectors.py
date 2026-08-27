"""Vector conversions used by directional area templates."""

from __future__ import annotations

import math

from .area_models import Point2D, Vector2D
from .primitives import Position

EPSILON = 1e-9

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


def point_from_position(position: Position) -> Point2D:
    """Convert a grid position to its continuous coordinate point."""

    return Point2D(float(position.x) + 0.5, float(position.y) + 0.5)


def directional_origin_point(origin: Position, direction: Vector2D) -> Point2D:
    """Place a directional template at the source cell edge facing its aim."""

    return translate(point_from_position(origin), direction, 0.5)


def vector_from_direction(direction: str) -> Vector2D:
    """Convert a named grid direction into a unit vector."""

    if direction not in DIRECTION_VECTORS:
        raise ValueError(f"Unsupported direction: {direction!r}.")
    dx, dy = DIRECTION_VECTORS[direction]
    return normalize_vector(Vector2D(float(dx), float(dy)))


def vector_between_positions(origin: Position, target: Position) -> Vector2D:
    """Return the displacement from one grid position to another."""

    dx = float(target.x - origin.x)
    dy = float(target.y - origin.y)
    return normalize_vector(Vector2D(dx, dy))


def normalize_vector(vector: Vector2D) -> Vector2D:
    """Scale a nonzero vector to unit length while preserving direction."""

    magnitude = math.hypot(vector.x, vector.y)
    if magnitude <= EPSILON:
        raise ValueError("Direction vector must be non-zero.")
    return Vector2D(vector.x / magnitude, vector.y / magnitude)


def translate(point: Point2D, direction: Vector2D, distance: float) -> Point2D:
    """Move a point by a scaled vector."""

    return Point2D(
        point.x + (direction.x * distance),
        point.y + (direction.y * distance),
    )


def perpendicular(direction: Vector2D) -> Vector2D:
    """Rotate a vector ninety degrees counterclockwise."""

    return Vector2D(-direction.y, direction.x)


def distance_squared(point_a: Point2D, point_b: Point2D) -> float:
    """Return squared Euclidean distance without taking a square root."""

    delta_x = point_a.x - point_b.x
    delta_y = point_a.y - point_b.y
    return (delta_x * delta_x) + (delta_y * delta_y)
