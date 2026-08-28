"""Validate spell-specific targeting and area metadata."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from srd_arena.content.capabilities import (
    Ability,
    ConditionRequirementSchema,
    CreatureTypeRequirementSchema,
    EffectDurationSchema,
    NonNegativeInt,
    NotAffectedRequirementSchema,
    PositiveInt,
    SizeRequirementSchema,
)

from .base import SpellCapabilitySchemaModel


class CreatureTraitRequirementSchema(SpellCapabilitySchemaModel):
    """Encode the ``creature_trait`` spell-targeting variant with trait."""

    type: Literal["creature_trait"]
    trait: str = Field(min_length=1)


class ConditionImmunityRequirementSchema(SpellCapabilitySchemaModel):
    """Encode the ``condition_immunity`` spell-targeting variant with condition."""

    type: Literal["condition_immunity"]
    condition: str = Field(min_length=1)


class SpellComponentRequirementSchema(SpellCapabilitySchemaModel):
    """Encode the ``spell_component`` spell-targeting variant with component."""

    type: Literal["spell_component"]
    component: Literal["verbal", "somatic", "material"]


class AttackSourceRequirementSchema(SpellCapabilitySchemaModel):
    """Encode the ``attack_source`` spell-targeting variant with source and mode."""

    type: Literal["attack_source"]
    source: Literal["weapon", "unarmed_strike", "spell", "any"]
    mode: Literal["melee", "ranged", "any"] = "any"


class WillingRequirementSchema(SpellCapabilitySchemaModel):
    """Encode the ``willing`` spell-targeting variant."""

    type: Literal["willing"]


class FreeHandRequirementSchema(SpellCapabilitySchemaModel):
    """Encode the ``free_hand`` spell-targeting variant."""

    type: Literal["free_hand"]


class PerceptionRequirementSchema(SpellCapabilitySchemaModel):
    """Encode the ``perception`` spell-targeting variant with sense and subject."""

    type: Literal["perception"]
    sense: Literal["see", "hear"]
    subject: Literal["source", "target", "each_other"] = "source"


class HitPointRequirementSchema(SpellCapabilitySchemaModel):
    """Encode the ``hit_points`` spell-targeting variant with comparison and value."""

    type: Literal["hit_points"]
    comparison: Literal["less_than", "at_most", "at_least", "greater_than"]
    value: NonNegativeInt


class RelationshipRequirementSchema(SpellCapabilitySchemaModel):
    """Encode the ``relationship`` spell-targeting variant with relationship."""

    type: Literal["relationship"]
    relationship: str = Field(min_length=1)
    established_by: Literal["this_spell", "source", "any"] = "any"


class AnyRequirementSchema(SpellCapabilitySchemaModel):
    """Encode the ``any`` spell-targeting variant with requirements."""

    type: Literal["any"]
    requirements: list[SpellRequirementSchema] = Field(min_length=1)


class AllRequirementSchema(SpellCapabilitySchemaModel):
    """Encode the ``all`` spell-targeting variant with requirements."""

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
    """Encode the ``roll_modifier`` spell-targeting variant with roll and mode."""

    type: Literal["roll_modifier"]
    roll: Literal["saving_throw"]
    mode: Literal["advantage", "disadvantage", "add", "subtract"]
    ability: Ability | None = None
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    value: int | None = None
    duration: EffectDurationSchema | None = None
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)


class TargetCountSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-targeting fields with minimum and maximum."""

    minimum: NonNegativeInt = 1
    maximum: PositiveInt | Literal["spellcasting_modifier", "all"] = 1

    @model_validator(mode="after")
    def validate_bounds(self) -> TargetCountSchema:
        """Reject a numeric minimum greater than the maximum.

        >>> from pydantic import ValidationError
        >>> try:
        ...     TargetCountSchema(minimum=3, maximum=2)
        ... except ValidationError as error:
        ...     "minimum cannot exceed maximum" in str(error)
        True
        """
        if isinstance(self.maximum, int) and self.minimum > self.maximum:
            raise ValueError("Target count minimum cannot exceed maximum.")
        return self


class SelfSpellTargetSchema(SpellCapabilitySchemaModel):
    """Encode the ``self`` spell-targeting variant."""

    type: Literal["self"]


class CreatureSpellTargetSchema(SpellCapabilitySchemaModel):
    """Encode the ``creature`` spell-targeting variant with count and disposition."""

    type: Literal["creature"]
    count: TargetCountSchema = Field(default_factory=TargetCountSchema)
    disposition: Literal[
        "any", "ally", "enemy", "willing", "source", "trigger_target"
    ] = "any"
    selection: Literal["all", "choose", "choose_up_to"] = "choose"
    line_of_sight: bool = False
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)


class ObjectSpellTargetSchema(SpellCapabilitySchemaModel):
    """Encode the ``object`` spell-targeting variant with count and carried."""

    type: Literal["object"]
    count: TargetCountSchema = Field(default_factory=TargetCountSchema)
    carried: Literal["allowed", "required", "forbidden"] = "allowed"
    worn: Literal["allowed", "required", "forbidden"] = "allowed"
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)


class PointSpellTargetSchema(SpellCapabilitySchemaModel):
    """Encode the ``point`` spell-targeting variant with surface and line of sight."""

    type: Literal["point"]
    surface: Literal["any", "solid", "ground"] = "any"
    line_of_sight: bool = False


class EventSpellTargetSchema(SpellCapabilitySchemaModel):
    """Encode the ``event_target`` spell-targeting variant with binding."""

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
    """Define the authored spell-targeting fields with shape and radius feet."""

    shape: Literal[
        "sphere", "cone", "cube", "line", "cylinder", "emanation", "wall", "ring"
    ]
    radius_feet: PositiveInt | None = None
    length_feet: PositiveInt | None = None
    width_feet: PositiveInt | None = None
    height_feet: PositiveInt | None = None
    diameter_feet: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_dimensions(self) -> AreaGeometrySchema:
        """Require the dimensions needed by the selected area shape.

        >>> AreaGeometrySchema(shape="line", length_feet=100, width_feet=5).width_feet
        5
        >>> from pydantic import ValidationError
        >>> try:
        ...     AreaGeometrySchema(shape="sphere")
        ... except ValidationError as error:
        ...     "requires radius_feet" in str(error)
        True
        """
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
    """Encode the ``area`` spell-targeting variant with origin and geometry."""

    type: Literal["area"]
    origin: Literal["self", "point_in_range", "target", "spell_entity", "event_target"]
    geometry: AreaGeometrySchema
    affects: Literal["creatures", "objects", "creatures_and_objects"] = "creatures"
    occupants: Literal["all", "allies", "enemies", "chosen"] = "all"
    chosen_count: TargetCountSchema | None = None
    excludes_source: bool = False
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_chosen_count(self) -> AreaSpellTargetSchema:
        """Require a target count when area occupants are chosen.

        >>> from pydantic import ValidationError
        >>> try:
        ...     AreaSpellTargetSchema(type="area", origin="self",
        ...         geometry={"shape": "sphere", "radius_feet": 10}, occupants="chosen")
        ... except ValidationError as error:
        ...     "require chosen_count" in str(error)
        True
        """
        if self.occupants == "chosen" and self.chosen_count is None:
            raise ValueError("Chosen area occupants require chosen_count.")
        return self


class CompositeAreaComponentSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-targeting fields with geometry and minimum."""

    geometry: AreaGeometrySchema
    minimum: PositiveInt = 1
    maximum: PositiveInt

    @model_validator(mode="after")
    def validate_bounds(self) -> CompositeAreaComponentSchema:
        """Reject a composite minimum greater than its maximum.

        >>> from pydantic import ValidationError
        >>> try:
        ...     CompositeAreaComponentSchema(
        ...         geometry={"shape": "cube", "length_feet": 10}, minimum=3, maximum=2)
        ... except ValidationError as error:
        ...     "minimum cannot exceed maximum" in str(error)
        True
        """
        if self.minimum > self.maximum:
            raise ValueError("Composite area minimum cannot exceed maximum.")
        return self


class CompositeAreaSpellTargetSchema(SpellCapabilitySchemaModel):
    """Encode the ``composite_area`` spell-targeting variant with origin and component."""

    type: Literal["composite_area"]
    origin: Literal["point_in_range"] = "point_in_range"
    component: CompositeAreaComponentSchema
    contiguity: Literal["none", "edge", "edge_or_corner", "touching_3d"] = "edge"
    require_connected_set: bool = True
    overlap: Literal["forbidden", "union"] = "union"
    occupants: Literal["all", "allies", "enemies", "chosen"] = "all"


class SpellEntityTargetSchema(SpellCapabilitySchemaModel):
    """Encode the ``spell_entity`` spell-targeting variant with ownership."""

    type: Literal["spell_entity"]
    ownership: Literal["source", "any"] = "source"
    entity_kinds: list[str] = Field(default_factory=list)


class TargetChoiceOptionSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-targeting fields with id and label."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    target: SpellTargetSchema


class ChoiceSpellTargetSchema(SpellCapabilitySchemaModel):
    """Encode the ``choice`` spell-targeting variant with options."""

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
