from dataclasses import dataclass

from .areas import DEFAULT_CELL_COVERAGE_THRESHOLD


@dataclass(frozen=True)
class GeometryConfig:
    directional_area_cell_coverage_threshold: float = DEFAULT_CELL_COVERAGE_THRESHOLD
