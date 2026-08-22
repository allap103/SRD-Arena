"""Monster-action effects retained as declarations but not executed."""

from typing import Annotated, Literal

from pydantic import Field

from srd_arena.content.capabilities.schemas.base import (
    CapabilitySchemaModel,
    NonNegativeInt,
    PositiveInt,
)
from srd_arena.content.capabilities.schemas.durations import EffectDurationSchema
from srd_arena.content.capabilities.schemas.effects import ExecutableEffectSchema
from srd_arena.content.capabilities.schemas.requirements import (
    CreatureTypeRequirementSchema,
)


class ForcedMovementDeclarationSchema(CapabilitySchemaModel):
    type: Literal["forced_movement"]
    direction: Literal["away", "toward", "chosen"]
    distance_feet: PositiveInt
    up_to: bool = True


class SpeedMultiplierDeclarationSchema(CapabilitySchemaModel):
    type: Literal["speed_multiplier"]
    numerator: NonNegativeInt
    denominator: PositiveInt
    duration: EffectDurationSchema


class ProhibitReactionsDeclarationSchema(CapabilitySchemaModel):
    type: Literal["prohibit_reactions"]
    duration: EffectDurationSchema


class TurnEconomyRestrictionDeclarationSchema(CapabilitySchemaModel):
    type: Literal["turn_economy_restriction"]
    choose_between: list[Literal["action", "bonus_action"]] = Field(
        min_length=2,
        max_length=2,
    )
    duration: EffectDurationSchema


class ControlDeclarationSchema(CapabilitySchemaModel):
    type: Literal["control"]
    controller: Literal["source"]
    communication: Literal["telepathy"] | None = None
    communication_range_feet: PositiveInt | Literal["unlimited"] | None = None
    control_range_feet: PositiveInt | None = None
    duration: EffectDurationSchema


class GainMemoriesDeclarationSchema(CapabilitySchemaModel):
    type: Literal["gain_memories"]
    requirement: CreatureTypeRequirementSchema
    trigger: Literal["reduced_to_zero_by_action"]


DeclaredOnlyEffectSchema = Annotated[
    ForcedMovementDeclarationSchema
    | SpeedMultiplierDeclarationSchema
    | ProhibitReactionsDeclarationSchema
    | TurnEconomyRestrictionDeclarationSchema
    | ControlDeclarationSchema
    | GainMemoriesDeclarationSchema,
    Field(discriminator="type"),
]


DeclaredActionEffectSchema = Annotated[
    ExecutableEffectSchema | DeclaredOnlyEffectSchema,
    Field(discriminator="type"),
]
