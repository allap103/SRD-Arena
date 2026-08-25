"""Public facade for area templates and rasterization.

Callers work with this module or :mod:`srd_arena.domain.geometry`; the
implementation is split by concern into models, builders, vector helpers,
rasterization, and serialization.
"""

from .area_builders import (
    build_cone_area,
    build_cone_area_from_vector,
    build_cube_area,
    build_cube_area_from_vector,
    build_directional_area,
    build_line_area,
    build_line_area_from_vector,
    build_point_cube_area,
    build_radius_area,
)
from .area_models import (
    DEFAULT_CELL_COVERAGE_THRESHOLD,
    RASTERIZATION_POLICY,
    TOUCHED_CELL_POLICY,
    AreaOfEffect,
    ContinuousArea,
    Point2D,
    Vector2D,
)
from .area_rasterization import continuous_area_outline
from .area_serialization import (
    deserialize_continuous_area,
    serialize_area,
    serialize_continuous_area,
)
from .area_vectors import (
    directional_origin_point,
    normalize_vector,
    point_from_position,
    vector_between_positions,
    vector_from_direction,
)

__all__ = [
    "DEFAULT_CELL_COVERAGE_THRESHOLD",
    "RASTERIZATION_POLICY",
    "TOUCHED_CELL_POLICY",
    "AreaOfEffect",
    "ContinuousArea",
    "Point2D",
    "Vector2D",
    "build_cone_area",
    "build_cone_area_from_vector",
    "build_cube_area",
    "build_cube_area_from_vector",
    "build_directional_area",
    "build_line_area",
    "build_line_area_from_vector",
    "build_point_cube_area",
    "build_radius_area",
    "continuous_area_outline",
    "deserialize_continuous_area",
    "directional_origin_point",
    "normalize_vector",
    "point_from_position",
    "serialize_area",
    "serialize_continuous_area",
    "vector_between_positions",
    "vector_from_direction",
]
