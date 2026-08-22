from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from srd_arena.content.capabilities import (
    Ability,
    ConditionImmunityRequirementSchema,
    ConditionRequirementSchema,
    CreatureTraitRequirementSchema,
    CreatureTypeRequirementSchema,
    EffectDurationSchema,
    NonNegativeInt,
    NotAffectedRequirementSchema,
    PositiveInt,
    RelationshipRequirementSchema,
    SizeRequirementSchema,
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


class SpellSaveModifierSchema(SpellCapabilitySchemaModel):
    type: Literal["roll_modifier"]
    roll: Literal["saving_throw"]
    mode: Literal["advantage", "disadvantage", "add", "subtract"]
    ability: Ability | None = None
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    value: int | None = None
    duration: EffectDurationSchema | None = None
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)


class TargetCountSchema(SpellCapabilitySchemaModel):
    minimum: NonNegativeInt = 1
    maximum: PositiveInt | Literal["spellcasting_modifier", "all"] = 1

    @model_validator(mode="after")
    def validate_bounds(self) -> "TargetCountSchema":
        if isinstance(self.maximum, int) and self.minimum > self.maximum:
            raise ValueError("Target count minimum cannot exceed maximum.")
        return self


class SelfSpellTargetSchema(SpellCapabilitySchemaModel):
    type: Literal["self"]


class CreatureSpellTargetSchema(SpellCapabilitySchemaModel):
    type: Literal["creature"]
    count: TargetCountSchema = Field(default_factory=TargetCountSchema)
    disposition: Literal[
        "any", "ally", "enemy", "willing", "source", "trigger_target"
    ] = "any"
    selection: Literal["all", "choose", "choose_up_to"] = "choose"
    line_of_sight: bool = False
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)


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


class AreaGeometrySchema(SpellCapabilitySchemaModel):
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
        if self.shape == "cone" and self.length_feet is None:
            raise ValueError("Cone geometry requires length_feet.")
        if self.shape == "cube" and self.length_feet is None:
            raise ValueError("Cube geometry requires length_feet.")
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


class AreaSpellTargetSchema(SpellCapabilitySchemaModel):
    type: Literal["area"]
    origin: Literal["self", "point_in_range", "target", "spell_entity", "event_target"]
    geometry: AreaGeometrySchema
    affects: Literal["creatures", "objects", "creatures_and_objects"] = "creatures"
    occupants: Literal["all", "allies", "enemies", "chosen"] = "all"
    chosen_count: TargetCountSchema | None = None
    excludes_source: bool = False
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_chosen_count(self) -> "AreaSpellTargetSchema":
        if self.occupants == "chosen" and self.chosen_count is None:
            raise ValueError("Chosen area occupants require chosen_count.")
        return self


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
