from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Ability = Literal["str", "dex", "con", "int", "wis", "cha"]


class ActionMechanicsSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConditionRequirementSchema(ActionMechanicsSchemaModel):
    type: Literal["condition"]
    conditions: list[str] = Field(min_length=1)
    match: Literal["any", "all"] = "any"
    applied_by: Literal["source", "any"] = "any"


class CreatureTypeRequirementSchema(ActionMechanicsSchemaModel):
    type: Literal["creature_type"]
    creature_types: list[str] = Field(min_length=1)


class SizeRequirementSchema(ActionMechanicsSchemaModel):
    type: Literal["size"]
    maximum: str | None = None
    minimum: str | None = None


class NotAffectedRequirementSchema(ActionMechanicsSchemaModel):
    type: Literal["not_affected_by"]
    action: str = Field(min_length=1)


ActionRequirementSchema = Annotated[
    ConditionRequirementSchema
    | CreatureTypeRequirementSchema
    | SizeRequirementSchema
    | NotAffectedRequirementSchema,
    Field(discriminator="type"),
]


class SelfTargetSchema(ActionMechanicsSchemaModel):
    type: Literal["self"]


class CreatureTargetSchema(ActionMechanicsSchemaModel):
    type: Literal["creature"]
    count: PositiveInt = 1
    range_feet: NonNegativeInt
    line_of_sight: bool = False
    requirements: list[ActionRequirementSchema] = Field(default_factory=list)


class AreaTargetSchema(ActionMechanicsSchemaModel):
    type: Literal["area"]
    shape: Literal["cone", "cube", "line", "radius"]
    size_feet: PositiveInt
    width_feet: PositiveInt | None = None
    origin: Literal["self", "point_in_range"] = "self"
    range_feet: NonNegativeInt | None = None
    affects: Literal["creatures", "enemies", "allies", "objects", "all"] = (
        "creatures"
    )
    excludes_self: bool = True
    requirements: list[ActionRequirementSchema] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_area_dimensions(self) -> "AreaTargetSchema":
        if self.shape == "line" and self.width_feet is None:
            raise ValueError("Line areas require width_feet.")
        if self.origin == "point_in_range" and self.range_feet is None:
            raise ValueError("Point-origin areas require range_feet.")
        return self


ActionTargetSchema = Annotated[
    SelfTargetSchema | CreatureTargetSchema | AreaTargetSchema,
    Field(discriminator="type"),
]


class EndOfTurnDurationSchema(ActionMechanicsSchemaModel):
    type: Literal["end_of_turn"]
    creature: Literal["source", "target"]
    turn_offset: NonNegativeInt = 0


class StartOfTurnDurationSchema(ActionMechanicsSchemaModel):
    type: Literal["start_of_turn"]
    creature: Literal["source", "target"]
    turn_offset: NonNegativeInt = 0


class TimedDurationSchema(ActionMechanicsSchemaModel):
    type: Literal["timed"]
    amount: PositiveInt
    unit: Literal["round", "minute", "hour", "day"]


class UntilEventDurationSchema(ActionMechanicsSchemaModel):
    type: Literal["until_event"]
    events: list[
        Literal[
            "source_dies",
            "different_plane",
            "target_takes_damage",
            "adjacent_creature_wakes_target",
        ]
    ] = Field(min_length=1)
    match: Literal["any", "all"] = "any"


class PermanentDurationSchema(ActionMechanicsSchemaModel):
    type: Literal["permanent"]


EffectDurationSchema = Annotated[
    EndOfTurnDurationSchema
    | StartOfTurnDurationSchema
    | TimedDurationSchema
    | UntilEventDurationSchema
    | PermanentDurationSchema,
    Field(discriminator="type"),
]


class AttackRollModeRequirementSchema(ActionMechanicsSchemaModel):
    type: Literal["attack_roll_mode"]
    mode: Literal["normal", "advantage", "disadvantage"]


AttackHitRequirementSchema = Annotated[
    AttackRollModeRequirementSchema,
    Field(discriminator="type"),
]


class DamageEffectSchema(ActionMechanicsSchemaModel):
    type: Literal["damage"]
    dice: str = Field(pattern=r"^\d+d\d+$")
    bonus: int = 0
    modifier: Literal["none", "spellcasting_ability"] = "none"
    damage_type: str = Field(min_length=1)
    minimum: NonNegativeInt | None = None
    requirements: list[AttackHitRequirementSchema] = Field(
        default_factory=list
    )


class ConditionEffectSchema(ActionMechanicsSchemaModel):
    type: Literal["condition"]
    condition: str = Field(min_length=1)
    duration: EffectDurationSchema | None = None
    requirements: list[ActionRequirementSchema] = Field(default_factory=list)
    escape_dc: PositiveInt | None = None
    source_capacity: PositiveInt | None = None
    ends_on: list[
        Literal[
            "source_dies",
            "different_plane",
            "target_takes_damage",
            "adjacent_creature_wakes_target",
        ]
    ] = Field(default_factory=list)


class ForcedMovementEffectSchema(ActionMechanicsSchemaModel):
    type: Literal["forced_movement"]
    direction: Literal["away", "toward", "chosen"]
    distance_feet: PositiveInt
    up_to: bool = True


class SpeedMultiplierEffectSchema(ActionMechanicsSchemaModel):
    type: Literal["speed_multiplier"]
    numerator: NonNegativeInt
    denominator: PositiveInt
    duration: EffectDurationSchema


class ProhibitReactionEffectSchema(ActionMechanicsSchemaModel):
    type: Literal["prohibit_reactions"]
    duration: EffectDurationSchema


class TurnEconomyRestrictionEffectSchema(ActionMechanicsSchemaModel):
    type: Literal["turn_economy_restriction"]
    choose_between: list[Literal["action", "bonus_action"]] = Field(
        min_length=2,
        max_length=2,
    )
    duration: EffectDurationSchema


class RollModifierEffectSchema(ActionMechanicsSchemaModel):
    type: Literal["roll_modifier"]
    roll: Literal[
        "ability_check",
        "attack_roll",
        "damage_roll",
        "saving_throw",
        "d20_test",
    ]
    mode: Literal["advantage", "disadvantage", "add", "subtract"]
    subject: Literal["target", "attacks_against_target"] = "target"
    ignored_by_senses: list[
        Literal["blindsight", "darkvision", "truesight"]
    ] = Field(default_factory=list)
    ability: Ability | None = None
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    value: int | None = None
    duration: EffectDurationSchema | None = None
    requirements: list[ActionRequirementSchema] = Field(default_factory=list)


class ControlEffectSchema(ActionMechanicsSchemaModel):
    type: Literal["control"]
    controller: Literal["source"]
    communication: Literal["telepathy"] | None = None
    communication_range_feet: PositiveInt | Literal["unlimited"] | None = None
    control_range_feet: PositiveInt | None = None
    duration: EffectDurationSchema


class GainMemoriesEffectSchema(ActionMechanicsSchemaModel):
    type: Literal["gain_memories"]
    requirement: CreatureTypeRequirementSchema
    trigger: Literal["reduced_to_zero_by_action"]


ActionEffectSchema = Annotated[
    DamageEffectSchema
    | ConditionEffectSchema
    | ForcedMovementEffectSchema
    | SpeedMultiplierEffectSchema
    | ProhibitReactionEffectSchema
    | TurnEconomyRestrictionEffectSchema
    | RollModifierEffectSchema
    | ControlEffectSchema
    | GainMemoriesEffectSchema,
    Field(discriminator="type"),
]


class RepeatSaveSchema(ActionMechanicsSchemaModel):
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


class SaveOutcomeStageSchema(ActionMechanicsSchemaModel):
    effects: list[ActionEffectSchema] = Field(min_length=1)
    repeat_saves: list[RepeatSaveSchema] = Field(default_factory=list)


class UsesResourceSchema(ActionMechanicsSchemaModel):
    type: Literal["uses"]
    maximum: PositiveInt
    reset: Literal["short_rest", "long_rest", "day"]


class RechargeResourceSchema(ActionMechanicsSchemaModel):
    type: Literal["recharge"]
    die: Literal["d6"] = "d6"
    minimum: int = Field(ge=2, le=6)


ActionResourceSchema = Annotated[
    UsesResourceSchema | RechargeResourceSchema,
    Field(discriminator="type"),
]


class AttackActionMechanicsSchema(ActionMechanicsSchemaModel):
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
    def validate_attack_distances(self) -> "AttackActionMechanicsSchema":
        if "melee" in self.attack_modes and self.reach_feet is None:
            raise ValueError("Melee attacks require reach_feet.")
        if "ranged" in self.attack_modes and self.range_normal_feet is None:
            raise ValueError("Ranged attacks require range_normal_feet.")
        return self


class SavingThrowActionMechanicsSchema(ActionMechanicsSchemaModel):
    type: Literal["saving_throw"] = "saving_throw"
    target: ActionTargetSchema
    ability: Ability
    dc: PositiveInt
    failure: list[SaveOutcomeStageSchema] = Field(min_length=1)
    success: list[ActionEffectSchema] = Field(default_factory=list)
    success_damage: Literal["none", "half"] = "none"
    always: list[ActionEffectSchema] = Field(default_factory=list)
    resource: ActionResourceSchema | None = None


class AutomaticActionMechanicsSchema(ActionMechanicsSchemaModel):
    type: Literal["automatic"] = "automatic"
    target: ActionTargetSchema
    effects: list[ActionEffectSchema] = Field(min_length=1)
    resource: ActionResourceSchema | None = None


class SpellOptionSchema(ActionMechanicsSchemaModel):
    name: str = Field(min_length=1)
    source: str | None = None
    cast_level: PositiveInt | None = None
    uses: PositiveInt | Literal["at_will"] | None = None


class SpellcastingActionMechanicsSchema(ActionMechanicsSchemaModel):
    type: Literal["spellcasting"] = "spellcasting"
    ability: Ability
    spells: list[SpellOptionSchema] = Field(min_length=1)
    shared_resource: ActionResourceSchema | None = None


NonMultiattackMechanicsSchema = Annotated[
    AttackActionMechanicsSchema
    | SavingThrowActionMechanicsSchema
    | AutomaticActionMechanicsSchema
    | SpellcastingActionMechanicsSchema,
    Field(discriminator="type"),
]
