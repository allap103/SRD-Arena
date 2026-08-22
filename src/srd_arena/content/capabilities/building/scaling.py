"""Build domain scaling rules from authored scaling schemas."""

from collections.abc import Iterable

import srd_arena.domain.capabilities as domain

from srd_arena.content.capabilities.schemas import scaling


def build_scaling_rules(
    values: Iterable[scaling.CapabilityScalingSchema],
) -> tuple[domain.CapabilityScaling, ...]:
    built: list[domain.CapabilityScaling] = []
    for value in values:
        if isinstance(value, scaling.ResourceScalingSchema):
            built.append(
                domain.CapabilityScaling(
                    basis="resource_level",
                    above_level=(
                        "base_level"
                        if value.above_level == "spell_level"
                        else value.above_level
                    ),
                    per_level=tuple(
                        domain.ScalingIncrement(
                            increment.type,
                            increment.amount,
                            increment.damage_type,
                        )
                        for increment in value.per_level
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
                        for threshold in value.thresholds
                    ),
                )
            )
    return tuple(built)
