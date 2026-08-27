"""Validate how authored spell values change with cast or creature level."""

from typing import Literal

from pydantic import Field, model_validator

from srd_arena.content.capabilities import NonNegativeInt, PositiveInt

from .base import SpellCapabilitySchemaModel


class SlotScalingIncrementSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-scaling fields with amount and damage type."""

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
    """Encode the ``slot_level`` spell-scaling variant with above level and per level."""

    type: Literal["slot_level"] = "slot_level"
    above_level: NonNegativeInt | Literal["spell_level"] = "spell_level"
    per_level: list[SlotScalingIncrementSchema] = Field(min_length=1)


class CasterLevelScalingThresholdSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-scaling fields with minimum level."""

    minimum_level: PositiveInt
    projectile_count: PositiveInt


class CasterLevelScalingSchema(SpellCapabilitySchemaModel):
    """Encode the ``caster_level`` spell-scaling variant with thresholds."""

    type: Literal["caster_level"]
    thresholds: list[CasterLevelScalingThresholdSchema] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_thresholds(self) -> CasterLevelScalingSchema:
        """Require sorted unique thresholds beginning at level one.

        >>> scaling = CasterLevelScalingSchema(type="caster_level", thresholds=[
        ...     {"minimum_level": 1, "projectile_count": 1},
        ...     {"minimum_level": 5, "projectile_count": 2},
        ... ])
        >>> [entry.minimum_level for entry in scaling.thresholds]
        [1, 5]
        >>> from pydantic import ValidationError
        >>> try:
        ...     CasterLevelScalingSchema(type="caster_level", thresholds=[
        ...         {"minimum_level": 5, "projectile_count": 2}])
        ... except ValidationError as error:
        ...     "level 1 baseline" in str(error)
        True
        """
        levels = [threshold.minimum_level for threshold in self.thresholds]
        if levels != sorted(set(levels)):
            raise ValueError("Caster-level thresholds must be unique and sorted.")
        if levels[0] != 1:
            raise ValueError("Caster-level scaling must define a level 1 baseline.")
        return self
