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
    if not isinstance(value, str):
        return default
    normalized = value.strip().casefold()
    if not normalized:
        return default
    if len(normalized) == 1 and normalized.upper() in SIZE_ORDER:
        return normalized.upper()
    return SIZE_ALIASES.get(normalized, default)


def size_rank(size: str) -> int:
    try:
        return SIZE_ORDER.index(size.upper())
    except ValueError:
        return SIZE_ORDER.index("M")


def is_two_sizes_smaller(target_size: str, grappler_size: str) -> bool:
    return size_rank(target_size) <= size_rank(grappler_size) - 2


def can_grapple(target_size: str, grappler_size: str) -> bool:
    return size_rank(target_size) <= size_rank(grappler_size) + 1
