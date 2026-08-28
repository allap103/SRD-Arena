"""Compute screen-space overlays for aimed area capabilities."""

from __future__ import annotations

from collections.abc import Mapping

from srd_arena.domain.geometry import (
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

from ...presentation.models import BattlefieldView

AreaPayload = Mapping[str, object]


def display_area_overlay(
    area: AreaPayload | None,
    hover_point: tuple[float, float] | None,
    battlefield: BattlefieldView | None,
) -> AreaPayload | None:
    """Return the hover preview or the authored overlay ready for display.

    A point-centered area is hidden until the pointer supplies its origin.

    >>> area = {
    ...     "shape": "radius", "origin": {"x": 1, "y": 1},
    ...     "continuous_area": {
    ...         "shape": "radius", "origin": {"x": 1, "y": 1}, "radius": 1,
    ...     },
    ... }
    >>> display_area_overlay(area, None, None) is None
    True
    >>> view = BattlefieldView(5, 5, [], "")
    >>> overlay_origin(display_area_overlay(area, (3.0, 2.0), view))
    (3, 2)
    """

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
    """Read valid grid cells from a serialized area payload.

    >>> overlay_cells({
    ...     "cells": ({"x": 1, "y": 2}, {"x": "invalid", "y": 3})
    ... })
    {(1, 2)}
    >>> overlay_cells(None)
    set()
    """

    if not isinstance(area, Mapping):
        return set()
    cells = area.get("cells")
    if not isinstance(cells, (list, tuple)):
        return set()
    return {
        (cell["x"], cell["y"])
        for cell in cells
        if isinstance(cell, Mapping)
        and isinstance(cell.get("x"), int)
        and isinstance(cell.get("y"), int)
    }


def overlay_origin(area: AreaPayload | None) -> tuple[int, int] | None:
    """Read a valid grid origin from a serialized area payload.

    >>> overlay_origin({"origin": {"x": 2, "y": 3}})
    (2, 3)
    >>> overlay_origin({"origin": {"x": 2.5, "y": 3}}) is None
    True
    """

    if not isinstance(area, Mapping):
        return None
    origin = area.get("origin")
    if not isinstance(origin, Mapping):
        return None
    x = origin.get("x")
    y = origin.get("y")
    if not isinstance(x, int) or not isinstance(y, int):
        return None
    return (x, y)


def continuous_area(area: AreaPayload | None) -> ContinuousArea | None:
    """Deserialize the continuous geometry carried by an overlay payload.

    >>> payload = {
    ...     "continuous_area": {
    ...         "shape": "radius", "origin": {"x": 1, "y": 2}, "radius": 3,
    ...     }
    ... }
    >>> geometry = continuous_area(payload)
    >>> (geometry.shape, geometry.radius)
    ('radius', 3.0)
    """

    if not isinstance(area, Mapping):
        return None
    return deserialize_continuous_area(area.get("continuous_area"))


def area_overlay_label(area: AreaPayload) -> str:
    """Build the compact label displayed for an area template.

    >>> area_overlay_label({"shape": "cone"})
    'Cone AoE'
    >>> area_overlay_label({})
    'Area AoE'
    """

    shape = area.get("shape")
    label = str(shape).capitalize() if isinstance(shape, str) else "Area"
    return f"{label} AoE"


def preview_area_overlay(
    area: AreaPayload | None,
    hover_point: tuple[float, float] | None,
    battlefield: BattlefieldView | None,
) -> AreaPayload | None:
    """Place a serialized point or directional area at the hover position.

    >>> authored = serialize_area(
    ...     build_radius_area(Position(1, 1), 1, Grid(5, 5))
    ... )
    >>> view = BattlefieldView(5, 5, [], "")
    >>> preview = preview_area_overlay(authored, (3.0, 2.0), view)
    >>> overlay_origin(preview)
    (3, 2)
    >>> preview_area_overlay(authored, None, view) is None
    True
    """

    if area is None or hover_point is None or battlefield is None:
        return None
    origin = area.get("origin")
    if not isinstance(origin, Mapping):
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
                max(1, round(continuous.length)),
                grid,
            )
        )
    if continuous.shape == "radius" and continuous.radius is not None:
        return serialize_area(
            build_radius_area(
                preview_origin,
                max(1, round(continuous.radius)),
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
    size = max(1, round(continuous.length))
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
