"""Capability scaling calculations used while resolving a spell."""

import re

from ...capabilities import CapabilityDefinition


def scale_dice(
    base: str | None,
    increment: str | None,
    levels_above: int,
) -> str | None:
    if base is None or increment is None or levels_above <= 0:
        return base
    base_count, base_sides = parse_damage_dice(base)
    increment_count, increment_sides = parse_damage_dice(increment)
    if base_sides != increment_sides:
        raise ValueError("Healing scaling must use the base healing die.")
    return f"{base_count + increment_count * levels_above}d{base_sides}"


def scaled_damage_dice(
    dice: str,
    increment_count: int,
    increment_sides: int,
    levels_above: int,
) -> str:
    count, sides = parse_damage_dice(dice)
    if sides != increment_sides:
        raise ValueError("Slot damage scaling must use the base damage die.")
    return f"{count + increment_count * levels_above}d{sides}"


def actor_level_damage_dice(
    definition: CapabilityDefinition,
    actor_level: int,
) -> str | None:
    thresholds = sorted(
        (
            threshold
            for scaling in definition.scaling
            if scaling.basis == "actor_level"
            for threshold in scaling.thresholds
            if threshold.minimum_level <= actor_level
        ),
        key=lambda threshold: threshold.minimum_level,
    )
    for threshold in reversed(thresholds):
        for increment in threshold.increments:
            if increment.kind == "damage_dice" and isinstance(increment.amount, str):
                return increment.amount
    return None


def resource_dice_increment(
    definition: CapabilityDefinition,
    kind: str,
    damage_type: str | None = None,
) -> str | None:
    return next(
        (
            increment.amount
            for scaling in definition.scaling
            if scaling.basis == "resource_level"
            for increment in scaling.per_level
            if increment.kind == kind
            and isinstance(increment.amount, str)
            and (
                damage_type is None
                or increment.damage_type is None
                or increment.damage_type == damage_type
            )
        ),
        None,
    )


def resource_int_increment(
    definition: CapabilityDefinition,
    kind: str,
) -> int:
    return sum(
        increment.amount
        for scaling in definition.scaling
        if scaling.basis == "resource_level"
        for increment in scaling.per_level
        if increment.kind == kind and isinstance(increment.amount, int)
    )


def parse_damage_dice(expression: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)d(\d+)", expression)
    if match is None:
        raise ValueError(f"Unsupported damage dice expression: {expression!r}")
    return int(match.group(1)), int(match.group(2))
