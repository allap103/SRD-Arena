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
    """Convert a rasterized area and optional exact geometry into event data."""

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
    """Convert an exact geometric template into primitive event-safe fields."""

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
    """Reconstruct a continuous area from its event-safe serialized fields."""

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
