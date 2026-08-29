"""Validate spell outcomes that require spell-specific authoring fields."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, RootModel, model_validator

from srd_arena.content.capabilities import (
    Ability,
    ConditionEffectSchema,
    DamageEffectSchema,
    DerivedDifficultyClassSchema,
    EffectDurationSchema,
    ForcedMovementEffectSchema,
    NonNegativeInt,
    PositiveInt,
    ProhibitReactionEffectSchema,
    RollModifierEffectSchema,
    SpeedMultiplierEffectSchema,
    TurnEconomyRestrictionEffectSchema,
)
from srd_arena.content.capabilities import (
    AutomaticResolutionSchema as SharedAutomaticResolutionSchema,
)
from srd_arena.content.capabilities import (
    OutcomeSchema as SharedOutcomeSchema,
)
from srd_arena.content.capabilities import (
    SavingThrowResolutionSchema as SharedSavingThrowResolutionSchema,
)

from .base import SpellCapabilitySchemaModel
from .targeting import (
    SpellRequirementSchema,
    SpellSaveModifierSchema,
    SpellTargetSchema,
)


class HealingEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``healing`` spell-resolution variant with dice and bonus."""

    type: Literal["healing"]
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    bonus: int = 0
    modifier: Literal["none", "spellcasting_ability"] = "none"
    from_damage: Literal["none", "half_damage_dealt", "all_damage_dealt"] = "none"
    restore_to_maximum: bool = False
    pool: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_healing_source(self) -> HealingEffectSchema:
        """Require at least one source for the healing amount.

        >>> HealingEffectSchema(type="healing", dice="2d8").dice
        '2d8'
        >>> from pydantic import ValidationError
        >>> try:
        ...     HealingEffectSchema(type="healing")
        ... except ValidationError as error:
        ...     "requires a roll" in str(error)
        True
        """
        if (
            self.dice is None
            and self.bonus == 0
            and self.modifier == "none"
            and self.from_damage == "none"
            and not self.restore_to_maximum
            and self.pool is None
        ):
            raise ValueError(
                "Healing requires a roll, value, modifier, or damage source."
            )
        return self


class TemporaryHitPointsEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``temporary_hit_points`` spell-resolution variant with dice."""

    type: Literal["temporary_hit_points"]
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    value: NonNegativeInt = 0
    modifier: Literal["none", "spellcasting_ability"] = "none"
    trigger: Literal["application", "target_turn_start"] = "application"

    @model_validator(mode="after")
    def validate_temporary_hit_points(self) -> TemporaryHitPointsEffectSchema:
        """Require a roll, value, or modifier for temporary hit points.

        >>> TemporaryHitPointsEffectSchema(type="temporary_hit_points", value=5).value
        5
        >>> from pydantic import ValidationError
        >>> try:
        ...     TemporaryHitPointsEffectSchema(type="temporary_hit_points")
        ... except ValidationError as error:
        ...     "require a roll" in str(error)
        True
        """
        if self.dice is None and self.value == 0 and self.modifier == "none":
            raise ValueError("Temporary hit points require a roll, value, or modifier.")
        return self


class ArmorClassModifierEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``armor_class_modifier`` spell-resolution variant with value."""

    type: Literal["armor_class_modifier"]
    value: int
    duration: EffectDurationSchema | None = None


class RemoveEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``remove_effect`` spell-resolution variant with selection."""

    type: Literal["remove_effect"]
    selection: Literal["one", "all"] = "one"
    removable: list[
        Literal[
            "condition",
            "exhaustion_level",
            "curse",
            "ability_score_reduction",
            "hit_point_maximum_reduction",
            "ongoing_effect",
        ]
    ] = Field(min_length=1)
    conditions: list[str] = Field(default_factory=list)


class DamageResistanceEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``damage_resistance`` spell-resolution variant with damage types."""

    type: Literal["damage_resistance"]
    damage_types: list[str] = Field(min_length=1)
    selection: Literal["all", "choose_one"] = "all"
    duration: EffectDurationSchema | None = None


class DamageReductionEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``damage_reduction`` spell-resolution variant with damage types."""

    type: Literal["damage_reduction"]
    damage_types: list[str] = Field(min_length=1)
    selection: Literal["all", "choose_one"] = "all"
    dice: str = Field(pattern=r"^\d+d\d+$")
    limit: PositiveInt = 1
    period: Literal["turn"] = "turn"
    duration: EffectDurationSchema | None = None


class SpeedModifierEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``speed_modifier`` spell-resolution variant with feet and duration."""

    type: Literal["speed_modifier"]
    feet: int
    duration: EffectDurationSchema | None = None


class ConditionSaveAdvantageEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``condition_save_advantage`` spell-resolution variant."""

    type: Literal["condition_save_advantage"]
    conditions: list[str] = Field(min_length=1)
    duration: EffectDurationSchema | None = None


class DamageImmunityEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``damage_immunity`` spell-resolution variant with damage types."""

    type: Literal["damage_immunity"]
    damage_types: list[str] = Field(min_length=1)
    duration: EffectDurationSchema | None = None


class ConditionImmunityEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``condition_immunity`` spell-resolution variant with conditions."""

    type: Literal["condition_immunity"]
    conditions: list[str] = Field(min_length=1)
    suppress_existing: bool = False
    duration: EffectDurationSchema | None = None


class SenseEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``sense`` spell-resolution variant with sense and range feet."""

    type: Literal["sense"]
    sense: Literal["blindsight", "darkvision", "truesight"]
    range_feet: PositiveInt
    duration: EffectDurationSchema | None = None


class HitPointMaximumModifierEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``hit_point_maximum_modifier`` spell-resolution variant with value."""

    type: Literal["hit_point_maximum_modifier"]
    value: int
    also_modify_current: bool = False
    duration: EffectDurationSchema | None = None


class SpellEffectSchema(
    RootModel[
        Annotated[
            DamageEffectSchema
            | ConditionEffectSchema
            | ForcedMovementEffectSchema
            | SpeedMultiplierEffectSchema
            | ProhibitReactionEffectSchema
            | TurnEconomyRestrictionEffectSchema
            | RollModifierEffectSchema
            | HealingEffectSchema
            | TemporaryHitPointsEffectSchema
            | ArmorClassModifierEffectSchema
            | RemoveEffectSchema
            | DamageResistanceEffectSchema
            | DamageReductionEffectSchema
            | SpeedModifierEffectSchema
            | ConditionSaveAdvantageEffectSchema
            | DamageImmunityEffectSchema
            | ConditionImmunityEffectSchema
            | SenseEffectSchema
            | HitPointMaximumModifierEffectSchema,
            Field(discriminator="type"),
        ]
    ]
):
    """Define the authored spell-resolution fields."""

    pass


class OutcomeSchema(SharedOutcomeSchema[SpellEffectSchema]):
    """Validate the ordered effects produced by one spell-resolution branch."""

    end_spell: bool = False


class AutomaticResolutionSchema(SharedAutomaticResolutionSchema[OutcomeSchema]):
    """Define the authored spell-resolution fields."""

    pass


class SavingThrowResolutionSchema(
    SharedSavingThrowResolutionSchema[OutcomeSchema, OutcomeSchema]
):
    """Define the authored spell-resolution fields with ability and difficulty."""

    ability: Ability | None = None
    difficulty: DerivedDifficultyClassSchema = Field(
        default_factory=lambda: DerivedDifficultyClassSchema(type="spell_save_dc")
    )
    use_spell_metadata_ability: bool = True
    automatic_success: list[SpellRequirementSchema] = Field(default_factory=list)
    automatic_failure: list[SpellRequirementSchema] = Field(default_factory=list)
    save_modifiers: list[SpellSaveModifierSchema] = Field(default_factory=list)
    success: OutcomeSchema = Field(default_factory=OutcomeSchema)
    repeat_save: RepeatSaveProgressionSchema | None = None


class SpellAttackResolutionSchema(SpellCapabilitySchemaModel):
    """Encode the ``spell_attack`` spell-resolution variant with mode and attacks."""

    type: Literal["spell_attack"]
    mode: Literal["melee", "ranged"]
    attacks: PositiveInt = 1
    allocation: Literal["same_target", "same_or_different"] = "same_target"
    hit: OutcomeSchema
    miss: OutcomeSchema = Field(default_factory=OutcomeSchema)


class RepeatResolutionSchema(SpellCapabilitySchemaModel):
    """Encode the ``repeat`` spell-resolution variant with count and allocation."""

    type: Literal["repeat"]
    count: PositiveInt | Literal["spellcasting_modifier", "slot_scaled"]
    allocation: Literal[
        "same_target", "same_or_different", "different_targets", "propagating"
    ] = "same_or_different"
    simultaneous: bool = False
    propagation_range_feet: PositiveInt | None = None
    cannot_repeat_target: bool = False
    resolution: SpellResolutionSchema

    @model_validator(mode="after")
    def validate_propagation(self) -> RepeatResolutionSchema:
        """Require a range when repeated resolution propagates between targets.

        >>> nested = {"type": "automatic", "outcome": {}}
        >>> RepeatResolutionSchema(type="repeat", count=2, allocation="propagating",
        ...     propagation_range_feet=30, resolution=nested).propagation_range_feet
        30
        >>> from pydantic import ValidationError
        >>> try:
        ...     RepeatResolutionSchema(type="repeat", count=2,
        ...         allocation="propagating", resolution=nested)
        ... except ValidationError as error:
        ...     "requires a propagation range" in str(error)
        True
        """
        if self.allocation == "propagating" and self.propagation_range_feet is None:
            raise ValueError("Propagating resolution requires a propagation range.")
        return self


class SequenceStepSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-resolution fields with resolution and target."""

    resolution: SpellResolutionSchema
    target: SpellTargetSchema | None = None


class SequenceResolutionSchema(SpellCapabilitySchemaModel):
    """Encode the ``sequence`` spell-resolution variant with steps."""

    type: Literal["sequence"]
    steps: list[SequenceStepSchema] = Field(min_length=1)


class SpellResolutionSchema(
    RootModel[
        Annotated[
            AutomaticResolutionSchema
            | SavingThrowResolutionSchema
            | SpellAttackResolutionSchema
            | RepeatResolutionSchema
            | SequenceResolutionSchema,
            Field(discriminator="type"),
        ]
    ]
):
    """Define the authored spell-resolution fields."""

    pass


class RepeatSaveProgressionSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-resolution fields with trigger and ability."""

    trigger: Literal["turn_start", "turn_end", "source_turn_start", "source_turn_end"]
    ability: Ability | None = None
    on_success: SpellResolutionSchema = Field(
        default_factory=lambda: SpellResolutionSchema.model_validate(
            {"type": "automatic", "outcome": {"end_spell": True}}
        )
    )
    on_failure: SpellResolutionSchema | None = None
    successes_required: PositiveInt = 1
    failures_required: PositiveInt | None = None
    counters_need_not_be_consecutive: bool = True


RepeatResolutionSchema.model_rebuild()
SequenceResolutionSchema.model_rebuild()
RepeatSaveProgressionSchema.model_rebuild()
