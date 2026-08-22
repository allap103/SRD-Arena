"""Authored target schemas for executable capabilities."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import CapabilitySchemaModel, NonNegativeInt, PositiveInt
from .requirements import CapabilityRequirementSchema


class SelfTargetSchema(CapabilitySchemaModel):
    type: Literal["self"]


class ActionCreatureTargetSchema(CapabilitySchemaModel):
    type: Literal["creature"]
    count: PositiveInt = 1
    range_feet: NonNegativeInt
    line_of_sight: bool = False
    requirements: list[CapabilityRequirementSchema] = Field(default_factory=list)


class ActionAreaTargetSchema(CapabilitySchemaModel):
    type: Literal["area"]
    shape: Literal["cone", "cube", "line", "radius"]
    size_feet: PositiveInt
    width_feet: PositiveInt | None = None
    origin: Literal["self", "point_in_range"] = "self"
    range_feet: NonNegativeInt | None = None
    affects: Literal["creatures", "enemies", "allies", "objects", "all"] = "creatures"
    excludes_self: bool = True
    requirements: list[CapabilityRequirementSchema] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_area_dimensions(self) -> "ActionAreaTargetSchema":
        if self.shape == "line" and self.width_feet is None:
            raise ValueError("Line areas require width_feet.")
        if self.origin == "point_in_range" and self.range_feet is None:
            raise ValueError("Point-origin areas require range_feet.")
        return self


ActionTargetSchema = Annotated[
    SelfTargetSchema | ActionCreatureTargetSchema | ActionAreaTargetSchema,
    Field(discriminator="type"),
]


class TargetCountSchema(CapabilitySchemaModel):
    minimum: NonNegativeInt = 1
    maximum: PositiveInt | Literal["ability_modifier", "all"] = 1

    @model_validator(mode="after")
    def validate_bounds(self) -> "TargetCountSchema":
        if isinstance(self.maximum, int) and self.minimum > self.maximum:
            raise ValueError("Target count minimum cannot exceed maximum.")
        return self


class CreatureTargetSchema(CapabilitySchemaModel):
    """Executable creature selection shared by spells and other capabilities."""

    type: Literal["creature"]
    count: TargetCountSchema = Field(default_factory=TargetCountSchema)
    disposition: Literal[
        "any", "ally", "enemy", "willing", "source", "trigger_target"
    ] = "any"
    selection: Literal["all", "choose", "choose_up_to"] = "choose"
    line_of_sight: bool = False
    requirements: list[CapabilityRequirementSchema] = Field(default_factory=list)


class AreaGeometrySchema(CapabilitySchemaModel):
    shape: Literal[
        "sphere", "cone", "cube", "line", "cylinder", "emanation", "wall", "ring"
    ]
    radius_feet: PositiveInt | None = None
    length_feet: PositiveInt | None = None
    width_feet: PositiveInt | None = None
    height_feet: PositiveInt | None = None
    diameter_feet: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_dimensions(self) -> "AreaGeometrySchema":
        if self.shape in {"sphere", "emanation"} and self.radius_feet is None:
            raise ValueError(f"{self.shape.title()} geometry requires radius_feet.")
        if self.shape in {"cone", "cube"} and self.length_feet is None:
            raise ValueError(f"{self.shape.title()} geometry requires length_feet.")
        if self.shape == "line" and (
            self.length_feet is None or self.width_feet is None
        ):
            raise ValueError("Line geometry requires length_feet and width_feet.")
        if self.shape == "cylinder" and (
            self.radius_feet is None or self.height_feet is None
        ):
            raise ValueError("Cylinder geometry requires radius_feet and height_feet.")
        if self.shape == "wall" and (
            self.length_feet is None
            or self.width_feet is None
            or self.height_feet is None
        ):
            raise ValueError(
                "Wall geometry requires length_feet, width_feet, and height_feet."
            )
        if self.shape == "ring" and (
            self.diameter_feet is None
            or self.width_feet is None
            or self.height_feet is None
        ):
            raise ValueError(
                "Ring geometry requires diameter_feet, width_feet, and height_feet."
            )
        return self


class AreaTargetSchema(CapabilitySchemaModel):
    """Executable area selection shared by spells and other capabilities."""

    type: Literal["area"]
    origin: Literal[
        "self", "point_in_range", "target", "created_entity", "event_target"
    ]
    geometry: AreaGeometrySchema
    affects: Literal["creatures", "objects", "creatures_and_objects"] = "creatures"
    occupants: Literal["all", "allies", "enemies", "chosen"] = "all"
    chosen_count: TargetCountSchema | None = None
    excludes_source: bool = False
    requirements: list[CapabilityRequirementSchema] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_chosen_count(self) -> "AreaTargetSchema":
        if self.occupants == "chosen" and self.chosen_count is None:
            raise ValueError("Chosen area occupants require chosen_count.")
        return self


ExecutableTargetSchema = Annotated[
    SelfTargetSchema | CreatureTargetSchema | AreaTargetSchema,
    Field(discriminator="type"),
]
