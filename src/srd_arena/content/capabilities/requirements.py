from typing import Annotated, Literal

from pydantic import Field

from .base import CapabilitySchemaModel


class ConditionRequirementSchema(CapabilitySchemaModel):
    type: Literal["condition"]
    conditions: list[str] = Field(min_length=1)
    match: Literal["any", "all"] = "any"
    applied_by: Literal["source", "any"] = "any"


class CreatureTypeRequirementSchema(CapabilitySchemaModel):
    type: Literal["creature_type"]
    creature_types: list[str] = Field(min_length=1)


class SizeRequirementSchema(CapabilitySchemaModel):
    type: Literal["size"]
    maximum: str | None = None
    minimum: str | None = None


class NotAffectedRequirementSchema(CapabilitySchemaModel):
    type: Literal["not_affected_by"]
    action: str = Field(min_length=1)


class CreatureTraitRequirementSchema(CapabilitySchemaModel):
    type: Literal["creature_trait"]
    trait: str = Field(min_length=1)


class ConditionImmunityRequirementSchema(CapabilitySchemaModel):
    type: Literal["condition_immunity"]
    condition: str = Field(min_length=1)


class RelationshipRequirementSchema(CapabilitySchemaModel):
    type: Literal["relationship"]
    relationship: str = Field(min_length=1)
    established_by: Literal["this_spell", "source", "any"] = "any"


ActionRequirementSchema = Annotated[
    ConditionRequirementSchema
    | CreatureTypeRequirementSchema
    | SizeRequirementSchema
    | NotAffectedRequirementSchema
    | CreatureTraitRequirementSchema
    | ConditionImmunityRequirementSchema
    | RelationshipRequirementSchema,
    Field(discriminator="type"),
]


class AttackRollModeRequirementSchema(CapabilitySchemaModel):
    type: Literal["attack_roll_mode"]
    mode: Literal["normal", "advantage", "disadvantage"]


AttackHitRequirementSchema = Annotated[
    AttackRollModeRequirementSchema,
    Field(discriminator="type"),
]
