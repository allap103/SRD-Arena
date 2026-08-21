from typing import Annotated, Literal

from pydantic import Field, model_validator

from srd_arena.content.capabilities import (
    Ability,
    ActionEffectSchema,
    CapabilitySchemaModel,
    ActionTargetSchema,
    AutomaticResolutionSchema,
    CreatureTargetSchema,
    FixedDifficultyClassSchema,
    NonNegativeInt,
    OutcomeSchema,
    PositiveInt,
    SavingThrowResolutionSchema,
    TimedDurationSchema,
)


class RepeatSaveSchema(CapabilitySchemaModel):
    trigger: Literal["end_of_turn", "on_damage", "elapsed"]
    interval_amount: PositiveInt | None = None
    interval_unit: Literal["hour", "day"] | None = None
    distance_from_source_feet: NonNegativeInt | None = None
    effects_end_on_success: bool = True
    automatic_success_after: TimedDurationSchema | None = None

    @model_validator(mode="after")
    def validate_elapsed_interval(self) -> "RepeatSaveSchema":
        if self.trigger == "elapsed" and (
            self.interval_amount is None or self.interval_unit is None
        ):
            raise ValueError("Elapsed repeat saves require an interval.")
        return self


class SaveOutcomeStageSchema(OutcomeSchema[ActionEffectSchema]):
    effects: list[ActionEffectSchema] = Field(min_length=1)
    repeat_saves: list[RepeatSaveSchema] = Field(default_factory=list)


class RequiredActionOutcomeSchema(OutcomeSchema[ActionEffectSchema]):
    effects: list[ActionEffectSchema] = Field(min_length=1)


ActionOutcomeSchema = OutcomeSchema[ActionEffectSchema]
StagedFailureSchema = Annotated[
    list[SaveOutcomeStageSchema],
    Field(min_length=1),
]
AutomaticActionResolutionSchema = AutomaticResolutionSchema[
    RequiredActionOutcomeSchema
]


class SavingThrowActionResolutionSchema(
    SavingThrowResolutionSchema[StagedFailureSchema, ActionOutcomeSchema]
):
    ability: Ability
    difficulty: FixedDifficultyClassSchema
    success: ActionOutcomeSchema = Field(default_factory=ActionOutcomeSchema)
    always: ActionOutcomeSchema = Field(default_factory=ActionOutcomeSchema)


class UsesResourceSchema(CapabilitySchemaModel):
    type: Literal["uses"]
    maximum: PositiveInt
    reset: Literal["short_rest", "long_rest", "day"]


class RechargeResourceSchema(CapabilitySchemaModel):
    type: Literal["recharge"]
    die: Literal["d6"] = "d6"
    minimum: int = Field(ge=2, le=6)


ActionResourceSchema = Annotated[
    UsesResourceSchema | RechargeResourceSchema,
    Field(discriminator="type"),
]


class AttackCapabilitySchema(CapabilitySchemaModel):
    type: Literal["attack"] = "attack"
    attack_modes: list[Literal["melee", "ranged"]] = Field(min_length=1)
    attack_bonus: int
    target: CreatureTargetSchema
    reach_feet: PositiveInt | None = None
    range_normal_feet: PositiveInt | None = None
    range_long_feet: PositiveInt | None = None
    hit: list[ActionEffectSchema] = Field(min_length=1)
    resource: ActionResourceSchema | None = None

    @model_validator(mode="after")
    def validate_attack_distances(self) -> "AttackCapabilitySchema":
        if "melee" in self.attack_modes and self.reach_feet is None:
            raise ValueError("Melee attacks require reach_feet.")
        if "ranged" in self.attack_modes and self.range_normal_feet is None:
            raise ValueError("Ranged attacks require range_normal_feet.")
        return self


CreatureActionResolutionSchema = Annotated[
    SavingThrowActionResolutionSchema | AutomaticActionResolutionSchema,
    Field(discriminator="type"),
]


class CapabilitySchema(CapabilitySchemaModel):
    type: Literal["capability"] = "capability"
    target: ActionTargetSchema
    resolution: CreatureActionResolutionSchema
    resource: ActionResourceSchema | None = None


class SpellOptionSchema(CapabilitySchemaModel):
    name: str = Field(min_length=1)
    source: str | None = None
    cast_level: PositiveInt | None = None
    uses: PositiveInt | Literal["at_will"] | None = None


class SpellcastingCapabilitySchema(CapabilitySchemaModel):
    type: Literal["spellcasting"] = "spellcasting"
    ability: Ability
    spells: list[SpellOptionSchema] = Field(min_length=1)
    shared_resource: ActionResourceSchema | None = None


NonMultiattackCapabilitySchema = Annotated[
    AttackCapabilitySchema
    | CapabilitySchema
    | SpellcastingCapabilitySchema,
    Field(discriminator="type"),
]
