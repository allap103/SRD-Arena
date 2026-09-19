"""Deterministic JSON export for immutable engine records."""

import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum

from pydantic import BaseModel


def json_value(value: object) -> object:
    """Export only explicit record fields and JSON-compatible containers."""
    if isinstance(value, Enum):
        return json_value(value.value)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: json_value(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((json_value(item) for item in value), key=canonical_json)
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def canonical_json(value: object) -> str:
    """Encode reproducibly, rejecting NaN and infinity."""
    return json.dumps(
        json_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
