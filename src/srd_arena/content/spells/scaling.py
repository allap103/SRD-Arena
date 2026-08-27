"""Provide scaling support for the spells package."""

from typing import Literal

from pydantic import Field, model_validator

from srd_arena.content.capabilities import NonNegativeInt, PositiveInt

from .base import SpellCapabilitySchemaModel


class SlotScalingIncrementSchema(SpellCapabilitySchemaModel):
    """Validate authored slot scaling increment data."""

    type: Literal[
        "damage_dice",
        "healing_dice",
        "healing_bonus",
        "temporary_hit_points",
        "hit_point_maximum",
        "target_count",
        "projectile_count",
        "area_radius_feet",
        "duration",
    ]
    amount: PositiveInt | str
    damage_type: str | None = None


class SlotScalingSchema(SpellCapabilitySchemaModel):
    """Validate authored slot scaling data."""

    type: Literal["slot_level"] = "slot_level"
    above_level: NonNegativeInt | Literal["spell_level"] = "spell_level"
    per_level: list[SlotScalingIncrementSchema] = Field(min_length=1)


class CasterLevelScalingThresholdSchema(SpellCapabilitySchemaModel):
    """Validate authored caster level scaling threshold data."""

    minimum_level: PositiveInt
    projectile_count: PositiveInt


class CasterLevelScalingSchema(SpellCapabilitySchemaModel):
    """Validate authored caster level scaling data."""

    type: Literal["caster_level"]
    thresholds: list[CasterLevelScalingThresholdSchema] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_thresholds(self) -> CasterLevelScalingSchema:
        levels = [threshold.minimum_level for threshold in self.thresholds]
        if levels != sorted(set(levels)):
            raise ValueError("Caster-level thresholds must be unique and sorted.")
        if levels[0] != 1:
            raise ValueError("Caster-level scaling must define a level 1 baseline.")
        return self
