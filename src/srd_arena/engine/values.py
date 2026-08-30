"""Immutable value helpers for the public engine contract."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

type EngineValue = (
    str
    | int
    | float
    | bool
    | None
    | tuple[EngineValue, ...]
    | Mapping[str, EngineValue]
)


def freeze_value(value: object) -> EngineValue:
    """Return a recursively immutable engine-contract value.

    >>> frozen = freeze_value({"targets": ["goblin", "ogre"]})
    >>> tuple(frozen["targets"])
    ('goblin', 'ogre')
    >>> type(frozen).__name__
    'mappingproxy'
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, EngineValue] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise TypeError("Engine mappings require string keys.")
            frozen[key] = freeze_value(nested)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_value(item) for item in value)
    raise TypeError(f"Unsupported engine value type: {type(value).__name__}.")


def freeze_mapping(
    value: Mapping[str, object],
) -> Mapping[str, EngineValue]:
    """Return a recursively immutable string-keyed mapping.

    >>> frozen = freeze_mapping({"roll": {"dice": [4, 6]}})
    >>> frozen["roll"]["dice"]
    (4, 6)
    """

    frozen = freeze_value(value)
    assert isinstance(frozen, Mapping)
    return frozen
