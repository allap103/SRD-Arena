"""Serialize continuous and rasterized area representations."""

from __future__ import annotations

from collections.abc import Mapping

from .area_models import (
    RASTERIZATION_POLICY,
    AreaOfEffect,
    ContinuousArea,
    Point2D,
    Vector2D,
)


def serialize_area(area: AreaOfEffect | None) -> dict[str, object] | None:
    """Convert a rasterized area and optional exact geometry into event data.

    >>> from .primitives import Position
    >>> area = AreaOfEffect("line", Position(0, 0), (Position(1, 0),))
    >>> payload = serialize_area(area)
    >>> (payload["shape"], payload["cells"])
    ('line', [{'x': 1, 'y': 0}])
    >>> serialize_area(None) is None
    True
    """

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


def serialize_continuous_area(area: ContinuousArea) -> dict[str, object]:
    """Convert an exact geometric template into primitive event-safe fields.

    >>> area = ContinuousArea("radius", Point2D(1.5, 2.5), radius=3.0)
    >>> serialize_continuous_area(area)["radius"]
    3.0
    """

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
    """Reconstruct a continuous area from its event-safe serialized fields.

    >>> original = ContinuousArea(
    ...     "line", Point2D(1.0, 2.0), Vector2D(1.0, 0.0), length=4.0)
    >>> deserialize_continuous_area(serialize_continuous_area(original)) == original
    True
    >>> deserialize_continuous_area("not a mapping") is None
    True
    """

    if not isinstance(payload, Mapping):
        return None
    shape = payload.get("shape")
    origin = payload.get("origin")
    if (
        not isinstance(shape, str)
        or not isinstance(origin, Mapping)
        or not isinstance(origin.get("x"), (int, float))
        or not isinstance(origin.get("y"), (int, float))
    ):
        return None
    direction_payload = payload.get("direction")
    direction = None
    if (
        isinstance(direction_payload, Mapping)
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
        length=_optional_float(payload.get("length")),
        width=_optional_float(payload.get("width")),
        radius=_optional_float(payload.get("radius")),
        rasterization_policy=(
            str(payload["rasterization_policy"])
            if isinstance(payload.get("rasterization_policy"), str)
            else RASTERIZATION_POLICY
        ),
        coverage_threshold=_optional_float(payload.get("coverage_threshold")),
    )


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
