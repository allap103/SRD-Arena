"""Provide config support for the geometry package."""

from dataclasses import dataclass

from .areas import DEFAULT_CELL_COVERAGE_THRESHOLD


@dataclass(frozen=True)
class GeometryConfig:
    """Represent a geometry config."""

    directional_area_cell_coverage_threshold: float = DEFAULT_CELL_COVERAGE_THRESHOLD
