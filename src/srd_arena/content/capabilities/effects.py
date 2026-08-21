from typing import Annotated, Literal

from pydantic import Field

from .base import Ability, CapabilitySchemaModel, NonNegativeInt, PositiveInt
from .durations import EffectDurationSchema
from .requirements import (
    ActionRequirementSchema,
    AttackHitRequirementSchema,
    CreatureTypeRequirementSchema,
)


class DamageEffectSchema(CapabilitySchemaModel):
    type: Literal["damage"]
    dice: str = Field(pattern=r"^\d+d\d+$")
    bonus: int = 0
    modifier: Literal["none", "spellcasting_ability"] = "none"
    damage_type: str = Field(min_length=1)
    minimum: NonNegativeInt | None = None
    requirements: list[AttackHitRequirementSchema] = Field(default_factory=list)


class ConditionEffectSchema(CapabilitySchemaModel):
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


class ForcedMovementEffectSchema(CapabilitySchemaModel):
    type: Literal["forced_movement"]
    direction: Literal["away", "toward", "chosen"]
    distance_feet: PositiveInt
    up_to: bool = True


class SpeedMultiplierEffectSchema(CapabilitySchemaModel):
    type: Literal["speed_multiplier"]
    numerator: NonNegativeInt
    denominator: PositiveInt
    duration: EffectDurationSchema


class ProhibitReactionEffectSchema(CapabilitySchemaModel):
    type: Literal["prohibit_reactions"]
    duration: EffectDurationSchema


class TurnEconomyRestrictionEffectSchema(CapabilitySchemaModel):
    type: Literal["turn_economy_restriction"]
    choose_between: list[Literal["action", "bonus_action"]] = Field(
        min_length=2,
        max_length=2,
    )
    duration: EffectDurationSchema


class RollModifierEffectSchema(CapabilitySchemaModel):
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
    ability_options: list[Ability] = Field(default_factory=list)
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    value: int | None = None
    duration: EffectDurationSchema | None = None
    requirements: list[ActionRequirementSchema] = Field(default_factory=list)


class ControlEffectSchema(CapabilitySchemaModel):
    type: Literal["control"]
    controller: Literal["source"]
    communication: Literal["telepathy"] | None = None
    communication_range_feet: PositiveInt | Literal["unlimited"] | None = None
    control_range_feet: PositiveInt | None = None
    duration: EffectDurationSchema


class GainMemoriesEffectSchema(CapabilitySchemaModel):
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
