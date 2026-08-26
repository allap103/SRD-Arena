from __future__ import annotations

from .....domain.geometry import (
    ContinuousArea,
    Grid,
    Position,
    Vector2D,
    build_directional_area,
    build_point_cube_area,
    build_radius_area,
    deserialize_continuous_area,
    serialize_area,
)
from ....shared.session import BattlefieldView

AreaPayload = dict[str, object]


def display_area_overlay(
    area: AreaPayload | None,
    hover_point: tuple[float, float] | None,
    battlefield: BattlefieldView | None,
) -> AreaPayload | None:
    """Return the hover preview or the authored overlay ready for display."""

    preview = preview_area_overlay(area, hover_point, battlefield)
    if preview is not None:
        return preview
    continuous = continuous_area(area)
    if (
        continuous is not None
        and continuous.direction is None
        and continuous.shape in {"radius", "cube"}
    ):
        return None
    return area


def overlay_cells(area: AreaPayload | None) -> set[tuple[int, int]]:
    """Read valid grid cells from a serialized area payload."""

    if not isinstance(area, dict):
        return set()
    cells = area.get("cells")
    if not isinstance(cells, list):
        return set()
    return {
        (cell["x"], cell["y"])
        for cell in cells
        if isinstance(cell, dict)
        and isinstance(cell.get("x"), int)
        and isinstance(cell.get("y"), int)
    }


def overlay_origin(area: AreaPayload | None) -> tuple[int, int] | None:
    """Read a valid grid origin from a serialized area payload."""

    if not isinstance(area, dict):
        return None
    origin = area.get("origin")
    if not isinstance(origin, dict):
        return None
    x = origin.get("x")
    y = origin.get("y")
    if not isinstance(x, int) or not isinstance(y, int):
        return None
    return (x, y)


def continuous_area(area: AreaPayload | None) -> ContinuousArea | None:
    """Deserialize the continuous geometry carried by an overlay payload."""

    if not isinstance(area, dict):
        return None
    return deserialize_continuous_area(area.get("continuous_area"))


def area_overlay_label(area: AreaPayload) -> str:
    """Build the compact label displayed for an area template."""

    shape = area.get("shape")
    label = str(shape).capitalize() if isinstance(shape, str) else "Area"
    return f"{label} AoE"


def preview_area_overlay(
    area: AreaPayload | None,
    hover_point: tuple[float, float] | None,
    battlefield: BattlefieldView | None,
) -> AreaPayload | None:
    """Place a serialized point or directional area at the hover position."""

    if area is None or hover_point is None or battlefield is None:
        return None
    origin = area.get("origin")
    if not isinstance(origin, dict):
        return None
    origin_x = origin.get("x")
    origin_y = origin.get("y")
    if not isinstance(origin_x, int) or not isinstance(origin_y, int):
        return None
    continuous = continuous_area(area)
    if continuous is None:
        return None
    preview_origin = Position(int(hover_point[0]), int(hover_point[1]))
    grid = Grid(width=battlefield.width, height=battlefield.height)
    if (
        continuous.shape == "cube"
        and continuous.direction is None
        and continuous.length is not None
    ):
        return serialize_area(
            build_point_cube_area(
                preview_origin,
                max(1, int(round(continuous.length))),
                grid,
            )
        )
    if continuous.shape == "radius" and continuous.radius is not None:
        return serialize_area(
            build_radius_area(
                preview_origin,
                max(1, int(round(continuous.radius))),
                grid,
            )
        )
    if preview_origin == Position(origin_x, origin_y):
        return None
    if (
        continuous.direction is None
        or continuous.shape not in {"cone", "line", "cube"}
        or continuous.length is None
    ):
        return None
    direction = Vector2D(
        hover_point[0] - continuous.origin.x,
        hover_point[1] - continuous.origin.y,
    )
    origin_position = Position(origin_x, origin_y)
    size = max(1, int(round(continuous.length)))
    coverage_threshold = (
        continuous.coverage_threshold
        if continuous.coverage_threshold is not None
        else 0.5
    )
    return serialize_area(
        build_directional_area(
            continuous.shape,
            origin_position,
            direction,
            size,
            grid,
            width_squares=continuous.width,
            coverage_threshold=coverage_threshold,
        )
    )
