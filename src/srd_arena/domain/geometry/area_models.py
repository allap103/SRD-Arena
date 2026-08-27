"""Value objects and policies for continuous and rasterized areas."""

from __future__ import annotations

from dataclasses import dataclass

from .primitives import Position

RASTERIZATION_POLICY = "coverage_threshold"
TOUCHED_CELL_POLICY = "touched_cell"
DEFAULT_CELL_COVERAGE_THRESHOLD = 0.5


@dataclass(frozen=True)
class Point2D:
    """Represent a point2 d."""

    x: float
    y: float


@dataclass(frozen=True)
class Vector2D:
    """Represent a vector2 d."""

    x: float
    y: float


@dataclass(frozen=True)
class ContinuousArea:
    """Represent a continuous area."""

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
    """Represent an area of effect."""

    shape: str
    origin: Position
    cells: tuple[Position, ...]
    continuous_area: ContinuousArea | None = None
    rasterization_policy: str = RASTERIZATION_POLICY
    coverage_threshold: float | None = None
