"""Configure project-level interpretations for ambiguous grid geometry rules."""

from dataclasses import dataclass

from .areas import DEFAULT_CELL_COVERAGE_THRESHOLD


@dataclass(frozen=True)
class GeometryConfig:
    """Hold thresholds used when continuous areas are rasterized onto the grid."""

    directional_area_cell_coverage_threshold: float = DEFAULT_CELL_COVERAGE_THRESHOLD
