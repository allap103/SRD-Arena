from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import CapabilitySchemaModel, NonNegativeInt, PositiveInt
from .requirements import ActionRequirementSchema


class SelfTargetSchema(CapabilitySchemaModel):
    type: Literal["self"]


class CreatureTargetSchema(CapabilitySchemaModel):
    type: Literal["creature"]
    count: PositiveInt = 1
    range_feet: NonNegativeInt
    line_of_sight: bool = False
    requirements: list[ActionRequirementSchema] = Field(default_factory=list)


class AreaTargetSchema(CapabilitySchemaModel):
    type: Literal["area"]
    shape: Literal["cone", "cube", "line", "radius"]
    size_feet: PositiveInt
    width_feet: PositiveInt | None = None
    origin: Literal["self", "point_in_range"] = "self"
    range_feet: NonNegativeInt | None = None
    affects: Literal["creatures", "enemies", "allies", "objects", "all"] = "creatures"
    excludes_self: bool = True
    requirements: list[ActionRequirementSchema] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_area_dimensions(self) -> AreaTargetSchema:
        if self.shape == "line" and self.width_feet is None:
            raise ValueError("Line areas require width_feet.")
        if self.origin == "point_in_range" and self.range_feet is None:
            raise ValueError("Point-origin areas require range_feet.")
        return self


ActionTargetSchema = Annotated[
    SelfTargetSchema | CreatureTargetSchema | AreaTargetSchema,
    Field(discriminator="type"),
]
