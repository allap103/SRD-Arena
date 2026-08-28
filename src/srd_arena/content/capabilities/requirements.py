"""Validate declarative restrictions on capability actors and targets."""

from typing import Annotated, Literal

from pydantic import Field

from .base import CapabilitySchemaModel


class ConditionRequirementSchema(CapabilitySchemaModel):
    """Encode the ``condition`` capability-requirement variant with conditions."""

    type: Literal["condition"]
    conditions: list[str] = Field(min_length=1)
    match: Literal["any", "all"] = "any"
    applied_by: Literal["source", "any"] = "any"


class CreatureTypeRequirementSchema(CapabilitySchemaModel):
    """Encode the ``creature_type`` capability-requirement variant with creature types."""

    type: Literal["creature_type"]
    creature_types: list[str] = Field(min_length=1)


class SizeRequirementSchema(CapabilitySchemaModel):
    """Encode the ``size`` capability-requirement variant with maximum and minimum."""

    type: Literal["size"]
    maximum: str | None = None
    minimum: str | None = None


class NotAffectedRequirementSchema(CapabilitySchemaModel):
    """Encode the ``not_affected_by`` capability-requirement variant with action."""

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
    """Encode the ``attack_roll_mode`` capability-requirement variant with mode."""

    type: Literal["attack_roll_mode"]
    mode: Literal["normal", "advantage", "disadvantage"]


AttackHitRequirementSchema = Annotated[
    AttackRollModeRequirementSchema,
    Field(discriminator="type"),
]
