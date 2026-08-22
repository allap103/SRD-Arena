from typing import overload

from srd_arena.content.spells.scaling import (
    CasterLevelScalingSchema,
    SlotScalingSchema,
)
from srd_arena.content.spells.schema import SpellSchema


@overload
def slot_scaling_value(
    raw: SpellSchema,
    kind: str,
    value_type: type[str],
) -> str | None: ...


@overload
def slot_scaling_value(
    raw: SpellSchema,
    kind: str,
    value_type: type[int],
) -> int | None: ...


def slot_scaling_value(
    raw: SpellSchema,
    kind: str,
    value_type: type[str] | type[int],
) -> str | int | None:
    assert raw.capability is not None
    return next(
        (
            increment.amount
            for scaling in raw.capability.scaling
            if isinstance(scaling, SlotScalingSchema)
            for increment in scaling.per_level
            if increment.type == kind and isinstance(increment.amount, value_type)
        ),
        None,
    )


def cantrip_damage_by_level(raw: SpellSchema) -> tuple[tuple[int, str], ...]:
    scaling_data = (raw.model_extra or {}).get("scalingLevelDice")
    if not isinstance(scaling_data, dict):
        return ()
    scaling = scaling_data.get("scaling")
    if not isinstance(scaling, dict):
        return ()
    return tuple(
        sorted(
            (int(level), dice)
            for level, dice in scaling.items()
            if isinstance(level, str) and level.isdigit() and isinstance(dice, str)
        )
    )


def slot_damage_increment(
    raw: SpellSchema,
    *,
    damage_types: set[str],
) -> str | None:
    assert raw.capability is not None
    return next(
        (
            increment.amount
            for scaling in raw.capability.scaling
            if isinstance(scaling, SlotScalingSchema)
            for increment in scaling.per_level
            if increment.type == "damage_dice"
            and isinstance(increment.amount, str)
            and (
                increment.damage_type is None
                or increment.damage_type in damage_types
            )
        ),
        None,
    )


def slot_target_increment(raw: SpellSchema) -> int:
    assert raw.capability is not None
    return sum(
        increment.amount
        for scaling in raw.capability.scaling
        if isinstance(scaling, SlotScalingSchema)
        for increment in scaling.per_level
        if increment.type in {"target_count", "projectile_count"}
        and isinstance(increment.amount, int)
    )


def target_count_by_caster_level(
    raw: SpellSchema,
) -> tuple[tuple[int, int], ...]:
    assert raw.capability is not None
    return tuple(
        (threshold.minimum_level, threshold.projectile_count)
        for scaling in raw.capability.scaling
        if isinstance(scaling, CasterLevelScalingSchema)
        for threshold in scaling.thresholds
    )
