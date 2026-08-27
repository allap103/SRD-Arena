"""Provide requirements support for the capabilities package."""

from typing import Annotated, Literal

from pydantic import Field

from .base import CapabilitySchemaModel


class ConditionRequirementSchema(CapabilitySchemaModel):
    """Validate authored condition requirement data."""

    type: Literal["condition"]
    conditions: list[str] = Field(min_length=1)
    match: Literal["any", "all"] = "any"
    applied_by: Literal["source", "any"] = "any"


class CreatureTypeRequirementSchema(CapabilitySchemaModel):
    """Validate authored creature type requirement data."""

    type: Literal["creature_type"]
    creature_types: list[str] = Field(min_length=1)


class SizeRequirementSchema(CapabilitySchemaModel):
    """Validate authored size requirement data."""

    type: Literal["size"]
    maximum: str | None = None
    minimum: str | None = None


class NotAffectedRequirementSchema(CapabilitySchemaModel):
    """Validate authored not affected requirement data."""

    type: Literal["not_affected_by"]
    action: str = Field(min_length=1)


ActionRequirementSchema = Annotated[
    ConditionRequirementSchema
    | CreatureTypeRequirementSchema
    | SizeRequirementSchema
    | NotAffectedRequirementSchema,
    Field(discriminator="type"),
]


class AttackRollModeRequirementSchema(CapabilitySchemaModel):
    """Validate authored attack roll mode requirement data."""

    type: Literal["attack_roll_mode"]
    mode: Literal["normal", "advantage", "disadvantage"]


AttackHitRequirementSchema = Annotated[
    AttackRollModeRequirementSchema,
    Field(discriminator="type"),
]
