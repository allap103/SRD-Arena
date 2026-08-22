from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from srd_arena.content.capabilities import (
    AreaGeometrySchema,
    AreaTargetSchema,
    ConditionImmunityRequirementSchema,
    ConditionRequirementSchema,
    CreatureTraitRequirementSchema,
    CreatureTargetSchema,
    CreatureTypeRequirementSchema,
    NonNegativeInt,
    NotAffectedRequirementSchema,
    PositiveInt,
    RelationshipRequirementSchema,
    SelfTargetSchema,
    SavingThrowModifierSchema,
    SizeRequirementSchema,
    TargetCountSchema,
)

from .base import SpellCapabilitySchemaModel


class SpellComponentRequirementSchema(SpellCapabilitySchemaModel):
    type: Literal["spell_component"]
    component: Literal["verbal", "somatic", "material"]


class AttackSourceRequirementSchema(SpellCapabilitySchemaModel):
    type: Literal["attack_source"]
    source: Literal["weapon", "unarmed_strike", "spell", "any"]
    mode: Literal["melee", "ranged", "any"] = "any"


class WillingRequirementSchema(SpellCapabilitySchemaModel):
    type: Literal["willing"]


class FreeHandRequirementSchema(SpellCapabilitySchemaModel):
    type: Literal["free_hand"]


class PerceptionRequirementSchema(SpellCapabilitySchemaModel):
    type: Literal["perception"]
    sense: Literal["see", "hear"]
    subject: Literal["source", "target", "each_other"] = "source"


class HitPointRequirementSchema(SpellCapabilitySchemaModel):
    type: Literal["hit_points"]
    comparison: Literal["less_than", "at_most", "at_least", "greater_than"]
    value: NonNegativeInt


class AnyRequirementSchema(SpellCapabilitySchemaModel):
    type: Literal["any"]
    requirements: list[SpellRequirementSchema] = Field(min_length=1)


class AllRequirementSchema(SpellCapabilitySchemaModel):
    type: Literal["all"]
    requirements: list[SpellRequirementSchema] = Field(min_length=1)


SpellRequirementSchema = Annotated[
    ConditionRequirementSchema
    | CreatureTypeRequirementSchema
    | SizeRequirementSchema
    | NotAffectedRequirementSchema
    | CreatureTraitRequirementSchema
    | ConditionImmunityRequirementSchema
    | SpellComponentRequirementSchema
    | AttackSourceRequirementSchema
    | WillingRequirementSchema
    | FreeHandRequirementSchema
    | PerceptionRequirementSchema
    | HitPointRequirementSchema
    | RelationshipRequirementSchema
    | AnyRequirementSchema
    | AllRequirementSchema,
    Field(discriminator="type"),
]


SpellSaveModifierSchema = SavingThrowModifierSchema


SelfSpellTargetSchema = SelfTargetSchema
CreatureSpellTargetSchema = CreatureTargetSchema


class ObjectSpellTargetSchema(SpellCapabilitySchemaModel):
    type: Literal["object"]
    count: TargetCountSchema = Field(default_factory=TargetCountSchema)
    carried: Literal["allowed", "required", "forbidden"] = "allowed"
    worn: Literal["allowed", "required", "forbidden"] = "allowed"
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)


class PointSpellTargetSchema(SpellCapabilitySchemaModel):
    type: Literal["point"]
    surface: Literal["any", "solid", "ground"] = "any"
    line_of_sight: bool = False


class EventSpellTargetSchema(SpellCapabilitySchemaModel):
    type: Literal["event_target"]
    binding: Literal[
        "triggering_actor",
        "triggering_target",
        "triggering_attacker",
        "triggering_caster",
        "effect_source",
        "effect_target",
    ]


AreaSpellTargetSchema = AreaTargetSchema


class CompositeAreaComponentSchema(SpellCapabilitySchemaModel):
    geometry: AreaGeometrySchema
    minimum: PositiveInt = 1
    maximum: PositiveInt

    @model_validator(mode="after")
    def validate_bounds(self) -> "CompositeAreaComponentSchema":
        if self.minimum > self.maximum:
            raise ValueError("Composite area minimum cannot exceed maximum.")
        return self


class CompositeAreaSpellTargetSchema(SpellCapabilitySchemaModel):
    type: Literal["composite_area"]
    origin: Literal["point_in_range"] = "point_in_range"
    component: CompositeAreaComponentSchema
    contiguity: Literal["none", "edge", "edge_or_corner", "touching_3d"] = "edge"
    require_connected_set: bool = True
    overlap: Literal["forbidden", "union"] = "union"
    occupants: Literal["all", "allies", "enemies", "chosen"] = "all"


class SpellEntityTargetSchema(SpellCapabilitySchemaModel):
    type: Literal["spell_entity"]
    ownership: Literal["source", "any"] = "source"
    entity_kinds: list[str] = Field(default_factory=list)


class TargetChoiceOptionSchema(SpellCapabilitySchemaModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    target: SpellTargetSchema


class ChoiceSpellTargetSchema(SpellCapabilitySchemaModel):
    type: Literal["choice"]
    options: list[TargetChoiceOptionSchema] = Field(min_length=1)


SpellTargetSchema = Annotated[
    SelfSpellTargetSchema
    | CreatureSpellTargetSchema
    | ObjectSpellTargetSchema
    | PointSpellTargetSchema
    | EventSpellTargetSchema
    | AreaSpellTargetSchema
    | CompositeAreaSpellTargetSchema
    | SpellEntityTargetSchema
    | ChoiceSpellTargetSchema,
    Field(discriminator="type"),
]

AnyRequirementSchema.model_rebuild()
AllRequirementSchema.model_rebuild()
TargetChoiceOptionSchema.model_rebuild()
ChoiceSpellTargetSchema.model_rebuild()
