"""Authored requirement schemas for capability use and targeting."""

from __future__ import annotations

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
    established_by: Literal["this_capability", "source", "any"] = "any"


class AttackSourceRequirementSchema(CapabilitySchemaModel):
    type: Literal["attack_source"]
    source: Literal["weapon", "unarmed_strike", "spell", "any"]
    mode: Literal["melee", "ranged", "any"] = "any"


class WillingRequirementSchema(CapabilitySchemaModel):
    type: Literal["willing"]


class FreeHandRequirementSchema(CapabilitySchemaModel):
    type: Literal["free_hand"]


class SpellComponentRequirementSchema(CapabilitySchemaModel):
    type: Literal["spell_component"]
    component: Literal["verbal", "somatic", "material"]


class PerceptionRequirementSchema(CapabilitySchemaModel):
    type: Literal["perception"]
    sense: Literal["see", "hear"]
    subject: Literal["source", "target", "each_other"] = "source"


class HitPointRequirementSchema(CapabilitySchemaModel):
    type: Literal["hit_points"]
    comparison: Literal["less_than", "at_most", "at_least", "greater_than"]
    value: int = Field(ge=0)


class AnyRequirementSchema(CapabilitySchemaModel):
    type: Literal["any"]
    requirements: list[CapabilityRequirementSchema] = Field(min_length=1)


class AllRequirementSchema(CapabilitySchemaModel):
    type: Literal["all"]
    requirements: list[CapabilityRequirementSchema] = Field(min_length=1)


CapabilityRequirementSchema = Annotated[
    ConditionRequirementSchema
    | CreatureTypeRequirementSchema
    | SizeRequirementSchema
    | NotAffectedRequirementSchema
    | CreatureTraitRequirementSchema
    | ConditionImmunityRequirementSchema
    | RelationshipRequirementSchema
    | AttackSourceRequirementSchema
    | WillingRequirementSchema
    | FreeHandRequirementSchema
    | SpellComponentRequirementSchema
    | PerceptionRequirementSchema
    | HitPointRequirementSchema
    | AnyRequirementSchema
    | AllRequirementSchema,
    Field(discriminator="type"),
]


AnyRequirementSchema.model_rebuild()
AllRequirementSchema.model_rebuild()


class AttackRollModeRequirementSchema(CapabilitySchemaModel):
    type: Literal["attack_roll_mode"]
    mode: Literal["normal", "advantage", "disadvantage"]


AttackHitRequirementSchema = Annotated[
    AttackRollModeRequirementSchema,
    Field(discriminator="type"),
]
