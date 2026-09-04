"""Validate declarative effects produced by authored capabilities."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import Ability, CapabilitySchemaModel, NonNegativeInt, PositiveInt
from .durations import EffectDurationSchema
from .requirements import (
    ActionRequirementSchema,
    AttackHitRequirementSchema,
    CreatureTypeRequirementSchema,
)


class DamageEffectSchema(CapabilitySchemaModel):
    """Encode the ``damage`` capability-effect variant with dice and bonus."""

    type: Literal["damage"]
    dice: str = Field(pattern=r"^\d+d\d+$")
    bonus: int = 0
    modifier: Literal["none", "spellcasting_ability"] = "none"
    damage_type: str = Field(min_length=1)
    minimum: NonNegativeInt | None = None
    requirements: list[AttackHitRequirementSchema] = Field(default_factory=list)


class AttackHitDamageEffectSchema(CapabilitySchemaModel):
    """Encode damage added when the effect source hits its marked target."""

    type: Literal["attack_hit_damage"]
    dice: str = Field(pattern=r"^\d+d\d+$")
    damage_type: str = Field(min_length=1)


class AttackHitRetaliationEffectSchema(CapabilitySchemaModel):
    """Deal fixed damage to a creature that hits the protected target."""

    type: Literal["attack_hit_retaliation"]
    value: PositiveInt
    damage_type: str = Field(min_length=1)
    attack_types: list[Literal["melee", "ranged"]] = Field(min_length=1)
    requires_temporary_hit_points: bool = False
    end_effect_when_depleted: bool = False

    @model_validator(mode="after")
    def validate_temporary_hit_point_lifecycle(
        self,
    ) -> AttackHitRetaliationEffectSchema:
        """Only end on depletion when temporary Hit Points gate the effect."""

        if self.end_effect_when_depleted and not self.requires_temporary_hit_points:
            raise ValueError(
                "Depletion ending requires requires_temporary_hit_points=true."
            )
        return self


class ConditionEffectSchema(CapabilitySchemaModel):
    """Encode the ``condition`` capability-effect variant with condition and duration."""

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
    """Encode the ``forced_movement`` capability-effect variant with direction."""

    type: Literal["forced_movement"]
    direction: Literal["away", "toward", "chosen"]
    distance_feet: PositiveInt
    up_to: bool = True


class SpeedMultiplierEffectSchema(CapabilitySchemaModel):
    """Encode the ``speed_multiplier`` capability-effect variant with numerator."""

    type: Literal["speed_multiplier"]
    numerator: NonNegativeInt
    denominator: PositiveInt
    duration: EffectDurationSchema


class ProhibitReactionEffectSchema(CapabilitySchemaModel):
    """Encode the ``prohibit_reactions`` capability-effect variant with duration."""

    type: Literal["prohibit_reactions"]
    duration: EffectDurationSchema


class TurnEconomyRestrictionEffectSchema(CapabilitySchemaModel):
    """Encode the ``turn_economy_restriction`` capability-effect variant."""

    type: Literal["turn_economy_restriction"]
    choose_between: list[Literal["action", "bonus_action"]] = Field(
        min_length=2,
        max_length=2,
    )
    duration: EffectDurationSchema


class CompelledTurnEffectSchema(CapabilitySchemaModel):
    """Encode a closed choice of instructions imposed on a target's next turn."""

    type: Literal["compelled_turn"]
    options: list[Literal["approach", "drop", "flee", "grovel", "halt"]] = Field(
        min_length=1
    )
    duration: EffectDurationSchema


class RollModifierEffectSchema(CapabilitySchemaModel):
    """Encode the ``roll_modifier`` capability-effect variant with roll and mode."""

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
    ignored_by_senses: list[Literal["blindsight", "darkvision", "truesight"]] = Field(
        default_factory=list
    )
    ability: Ability | None = None
    ability_options: list[Ability] = Field(default_factory=list)
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    value: int | None = None
    duration: EffectDurationSchema | None = None
    requirements: list[ActionRequirementSchema] = Field(default_factory=list)
    consume_on_use: bool = False

    @model_validator(mode="after")
    def validate_consumption_trigger(self) -> RollModifierEffectSchema:
        """Limit one-use modifiers to the saving-throw pipeline that consumes them."""

        if self.consume_on_use and self.roll != "saving_throw":
            raise ValueError("consume_on_use currently requires roll='saving_throw'.")
        return self


class ControlEffectSchema(CapabilitySchemaModel):
    """Encode the ``control`` capability-effect variant with controller."""

    type: Literal["control"]
    controller: Literal["source"]
    communication: Literal["telepathy"] | None = None
    communication_range_feet: PositiveInt | Literal["unlimited"] | None = None
    control_range_feet: PositiveInt | None = None
    duration: EffectDurationSchema


class GainMemoriesEffectSchema(CapabilitySchemaModel):
    """Encode the ``gain_memories`` capability-effect variant with requirement."""

    type: Literal["gain_memories"]
    requirement: CreatureTypeRequirementSchema
    trigger: Literal["reduced_to_zero_by_action"]


ActionEffectSchema = Annotated[
    DamageEffectSchema
    | AttackHitDamageEffectSchema
    | AttackHitRetaliationEffectSchema
    | ConditionEffectSchema
    | ForcedMovementEffectSchema
    | SpeedMultiplierEffectSchema
    | ProhibitReactionEffectSchema
    | TurnEconomyRestrictionEffectSchema
    | CompelledTurnEffectSchema
    | RollModifierEffectSchema
    | ControlEffectSchema
    | GainMemoriesEffectSchema,
    Field(discriminator="type"),
]
