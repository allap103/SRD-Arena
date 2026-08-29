"""Capability scaling calculations used while resolving a spell."""

import re

from srd_arena.domain.capabilities import CapabilityDefinition


def scale_dice(
    base: str | None,
    increment: str | None,
    levels_above: int,
) -> str | None:
    """Increase a dice expression by a number of additional dice.

    >>> scale_dice("2d8", "1d8", 3)
    '5d8'
    >>> scale_dice("2d8", "1d8", 0)
    '2d8'
    """

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
    """Apply resource-level damage-dice scaling to a base expression.

    >>> scaled_damage_dice("8d6", 1, 6, 2)
    '10d6'
    """

    count, sides = parse_damage_dice(dice)
    if sides != increment_sides:
        raise ValueError("Slot damage scaling must use the base damage die.")
    return f"{count + increment_count * levels_above}d{sides}"


def actor_level_damage_dice(
    definition: CapabilityDefinition,
    actor_level: int,
) -> str | None:
    """Resolve the highest damage-dice threshold reached by the actor.

    >>> from srd_arena.domain.capabilities import (
    ...     AutomaticResolution, CapabilityScaling, CapabilityTarget, Outcome,
    ...     ScalingIncrement, ScalingThreshold,
    ... )
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("self"), AutomaticResolution(Outcome()),
    ...     scaling=(CapabilityScaling("actor_level", thresholds=(
    ...         ScalingThreshold(1, (ScalingIncrement("damage_dice", "1d10"),)),
    ...         ScalingThreshold(5, (ScalingIncrement("damage_dice", "2d10"),)),
    ...     )),),
    ... )
    >>> actor_level_damage_dice(definition, 7)
    '2d10'
    """

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
    """Return a matching per-resource-level dice increment.

    >>> from srd_arena.domain.capabilities import (
    ...     AutomaticResolution, CapabilityScaling, CapabilityTarget, Outcome,
    ...     ScalingIncrement,
    ... )
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("self"), AutomaticResolution(Outcome()),
    ...     scaling=(CapabilityScaling("resource_level", per_level=(
    ...         ScalingIncrement("damage_dice", "1d6", "fire"),
    ...     )),),
    ... )
    >>> resource_dice_increment(definition, "damage_dice", "fire")
    '1d6'
    """

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
    """Sum per-resource-level integer increments of a requested kind.

    >>> from srd_arena.domain.capabilities import (
    ...     AutomaticResolution, CapabilityScaling, CapabilityTarget, Outcome,
    ...     ScalingIncrement,
    ... )
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("self"), AutomaticResolution(Outcome()),
    ...     scaling=(CapabilityScaling("resource_level", per_level=(
    ...         ScalingIncrement("target_count", 1),
    ...         ScalingIncrement("target_count", 2),
    ...     )),),
    ... )
    >>> resource_int_increment(definition, "target_count")
    3
    """

    return sum(
        increment.amount
        for scaling in definition.scaling
        if scaling.basis == "resource_level"
        for increment in scaling.per_level
        if increment.kind == kind and isinstance(increment.amount, int)
    )


def parse_damage_dice(expression: str) -> tuple[int, int]:
    """Parse an authored dice expression into its count and die size.

    >>> parse_damage_dice("8d6")
    (8, 6)
    >>> parse_damage_dice("2d10")
    (2, 10)
    """

    match = re.fullmatch(r"(\d+)d(\d+)", expression)
    if match is None:
        raise ValueError(f"Unsupported damage dice expression: {expression!r}")
    return int(match.group(1)), int(match.group(2))
