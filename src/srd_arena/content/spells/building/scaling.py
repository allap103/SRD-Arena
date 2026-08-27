import srd_arena.domain.capabilities as domain
from srd_arena.content.spells.scaling import (
    SlotScalingSchema,
)
from srd_arena.content.spells.schema import SpellSchema


def build_scaling(raw: SpellSchema) -> tuple[domain.CapabilityScaling, ...]:
    """Build provider-neutral resource- and actor-level scaling rules."""
    if raw.capability is None:
        return ()
    built: list[domain.CapabilityScaling] = []
    for scaling in raw.capability.scaling:
        if isinstance(scaling, SlotScalingSchema):
            built.append(
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
            built.append(
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
        built.append(
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
    return tuple(built)


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
