from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from srd_arena.content.capabilities.schemas.base import (
    CapabilitySchemaModel,
    PositiveInt,
)
from srd_arena.content.capabilities.schemas.requirements import (
    CapabilityRequirementSchema,
)
from srd_arena.content.capabilities.schemas.targets import (
    AreaGeometrySchema,
    AreaTargetSchema,
    CreatureTargetSchema,
    SelfTargetSchema,
    TargetCountSchema,
)


class ObjectTargetSchema(CapabilitySchemaModel):
    type: Literal["object"]
    count: TargetCountSchema = Field(default_factory=TargetCountSchema)
    carried: Literal["allowed", "required", "forbidden"] = "allowed"
    worn: Literal["allowed", "required", "forbidden"] = "allowed"
    requirements: list[CapabilityRequirementSchema] = Field(default_factory=list)


class PointTargetSchema(CapabilitySchemaModel):
    type: Literal["point"]
    surface: Literal["any", "solid", "ground"] = "any"
    line_of_sight: bool = False


class EventTargetSchema(CapabilitySchemaModel):
    type: Literal["event_target"]
    binding: Literal[
        "triggering_actor",
        "triggering_target",
        "triggering_attacker",
        "triggering_caster",
        "effect_source",
        "effect_target",
    ]


class CompositeAreaComponentSchema(CapabilitySchemaModel):
    geometry: AreaGeometrySchema
    minimum: PositiveInt = 1
    maximum: PositiveInt

    @model_validator(mode="after")
    def validate_bounds(self) -> "CompositeAreaComponentSchema":
        if self.minimum > self.maximum:
            raise ValueError("Composite area minimum cannot exceed maximum.")
        return self


class CompositeAreaTargetSchema(CapabilitySchemaModel):
    type: Literal["composite_area"]
    origin: Literal["point_in_range"] = "point_in_range"
    component: CompositeAreaComponentSchema
    contiguity: Literal["none", "edge", "edge_or_corner", "touching_3d"] = "edge"
    require_connected_set: bool = True
    overlap: Literal["forbidden", "union"] = "union"
    occupants: Literal["all", "allies", "enemies", "chosen"] = "all"


class CreatedEntityTargetSchema(CapabilitySchemaModel):
    type: Literal["created_entity"]
    ownership: Literal["source", "any"] = "source"
    entity_kinds: list[str] = Field(default_factory=list)


class TargetChoiceOptionSchema(CapabilitySchemaModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    target: CapabilityTargetSchema


class ChoiceTargetSchema(CapabilitySchemaModel):
    type: Literal["choice"]
    options: list[TargetChoiceOptionSchema] = Field(min_length=1)


CapabilityTargetSchema = Annotated[
    SelfTargetSchema
    | CreatureTargetSchema
    | ObjectTargetSchema
    | PointTargetSchema
    | EventTargetSchema
    | AreaTargetSchema
    | CompositeAreaTargetSchema
    | CreatedEntityTargetSchema
    | ChoiceTargetSchema,
    Field(discriminator="type"),
]

TargetChoiceOptionSchema.model_rebuild()
ChoiceTargetSchema.model_rebuild()
