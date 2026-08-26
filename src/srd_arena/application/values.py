"""Immutable value helpers for application-facing contracts."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

type ApplicationValue = (
    str
    | int
    | float
    | bool
    | None
    | tuple[ApplicationValue, ...]
    | Mapping[str, ApplicationValue]
)


def freeze_value(value: object) -> ApplicationValue:
    """Return a recursively immutable application value."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, ApplicationValue] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise TypeError("Application mappings require string keys.")
            frozen[key] = freeze_value(nested)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(item) for item in value)
    raise TypeError(
        f"Unsupported application value type: {type(value).__name__}."
    )


def freeze_mapping(
    value: Mapping[str, object],
) -> Mapping[str, ApplicationValue]:
    """Return a recursively immutable string-keyed mapping."""

    frozen = freeze_value(value)
    assert isinstance(frozen, Mapping)
    return frozen
