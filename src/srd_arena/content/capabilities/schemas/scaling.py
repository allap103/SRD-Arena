"""Authored scaling schemas for executable capabilities."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import CapabilitySchemaModel, NonNegativeInt, PositiveInt


class ScalingIncrementSchema(CapabilitySchemaModel):
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


class ResourceScalingSchema(CapabilitySchemaModel):
    type: Literal["resource_level"] = "resource_level"
    above_level: NonNegativeInt | Literal["base_level"] = "base_level"
    per_level: list[ScalingIncrementSchema] = Field(min_length=1)


class ActorLevelScalingThresholdSchema(CapabilitySchemaModel):
    minimum_level: PositiveInt
    increments: list[ScalingIncrementSchema] = Field(min_length=1)


class ActorLevelScalingSchema(CapabilitySchemaModel):
    type: Literal["actor_level"]
    thresholds: list[ActorLevelScalingThresholdSchema] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "ActorLevelScalingSchema":
        levels = [threshold.minimum_level for threshold in self.thresholds]
        if levels != sorted(set(levels)):
            raise ValueError("Actor-level thresholds must be unique and sorted.")
        if levels[0] != 1:
            raise ValueError("Actor-level scaling must define a level 1 baseline.")
        return self


CapabilityScalingSchema = Annotated[
    ResourceScalingSchema | ActorLevelScalingSchema,
    Field(discriminator="type"),
]
