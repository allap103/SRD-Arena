from typing import overload

from srd_arena.content.spells.scaling import (
    SlotScalingSchema,
)
from srd_arena.content.spells.schema import SpellSchema
import srd_arena.domain.capabilities as domain


def compile_scaling(raw: SpellSchema) -> tuple[domain.CapabilityScaling, ...]:
    """Compile provider-neutral resource- and actor-level scaling rules."""
    if raw.capability is None:
        return ()
    compiled: list[domain.CapabilityScaling] = []
    for scaling in raw.capability.scaling:
        if isinstance(scaling, SlotScalingSchema):
            compiled.append(
                domain.CapabilityScaling(
                    basis="resource_level",
                    above_level=(
                        "base_level"
                        if scaling.above_level == "spell_level"
                        else scaling.above_level
                    ),
                    per_level=tuple(
                        domain.ScalingIncrement(
                            increment.type,
                            increment.amount,
                            increment.damage_type,
                        )
                        for increment in scaling.per_level
                    ),
                )
            )
        else:
            compiled.append(
                domain.CapabilityScaling(
                    basis="actor_level",
                    thresholds=tuple(
                        domain.ScalingThreshold(
                            threshold.minimum_level,
                            (
                                domain.ScalingIncrement(
                                    "projectile_count",
                                    threshold.projectile_count,
                                ),
                            ),
                        )
                        for threshold in scaling.thresholds
                    ),
                )
            )
    damage_by_level = cantrip_damage_by_level(raw)
    if damage_by_level:
        compiled.append(
            domain.CapabilityScaling(
                basis="actor_level",
                thresholds=tuple(
                    domain.ScalingThreshold(
                        minimum_level,
                        (domain.ScalingIncrement("damage_dice", dice),),
                    )
                    for minimum_level, dice in damage_by_level
                ),
            )
        )
    return tuple(compiled)


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
