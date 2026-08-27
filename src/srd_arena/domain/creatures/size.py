"""Provide size support for the creatures package."""

from __future__ import annotations

SIZE_ORDER = ("T", "S", "M", "L", "H", "G", "C")
SIZE_ALIASES = {
    "tiny": "T",
    "small": "S",
    "medium": "M",
    "large": "L",
    "huge": "H",
    "gargantuan": "G",
    "colossal": "C",
}


def normalize_size(value: object, default: str = "M") -> str:
    """Normalize a size name or abbreviation to its canonical code.

    >>> normalize_size("gargantuan")
    'G'
    >>> normalize_size(None)
    'M'
    """

    if not isinstance(value, str):
        return default
    normalized = value.strip().casefold()
    if not normalized:
        return default
    if len(normalized) == 1 and normalized.upper() in SIZE_ORDER:
        return normalized.upper()
    return SIZE_ALIASES.get(normalized, default)


def size_rank(size: str) -> int:
    """Return a size's position in ascending size order.

    >>> size_rank("T") < size_rank("L")
    True
    """

    try:
        return SIZE_ORDER.index(size.upper())
    except ValueError:
        return SIZE_ORDER.index("M")


def is_two_sizes_smaller(target_size: str, grappler_size: str) -> bool:
    """Return whether a target is at least two sizes below a grappler.

    >>> is_two_sizes_smaller("S", "L")
    True
    >>> is_two_sizes_smaller("M", "L")
    False
    """

    return size_rank(target_size) <= size_rank(grappler_size) - 2


def can_grapple(target_size: str, grappler_size: str) -> bool:
    """Return whether the target is no more than one size larger.

    >>> can_grapple("L", "M")
    True
    >>> can_grapple("H", "M")
    False
    """

    return size_rank(target_size) <= size_rank(grappler_size) + 1
