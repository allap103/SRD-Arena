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


class SpellEntityStatisticsSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-resolution fields with armor class and hit points."""

    armor_class: PositiveInt | Literal["caster"] | None = None
    hit_points: PositiveInt | Literal["caster_maximum"] | None = None
    size: str | None = None
    ability_scores: dict[Ability, Annotated[int, Field(ge=1, le=30)]] = Field(
        default_factory=dict
    )
    condition_immunities: list[str] = Field(default_factory=list)
    damage_immunities: list[str] = Field(default_factory=list)


class TransformObjectEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``transform_object`` spell-resolution variant with creature by size."""

    type: Literal["transform_object"]
    creature_by_size: dict[str, str] = Field(min_length=1)
    restore_object_on_end: bool = True
    carry_damage_to_object: bool = True


class AccumulateDiceEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``accumulate_dice`` spell-resolution variant with counter and dice."""

    type: Literal["accumulate_dice"]
    counter: str = Field(min_length=1)
    dice: str = Field(pattern=r"^\d+d\d+$")
    maximum_dice: PositiveInt | None = None


class AccumulatedDamageEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``accumulated_damage`` spell-resolution variant with base dice."""

    type: Literal["accumulated_damage"]
    base_dice: str = Field(pattern=r"^\d+d\d+$")
    counter: str = Field(min_length=1)
    dice_per_counter: str = Field(pattern=r"^\d+d\d+$")
    damage_type: str = Field(min_length=1)


class GrantActionEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``grant_action`` spell-resolution variant with action."""

    type: Literal["grant_action"]
    action: GrantedActionSchema


class SummonEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``summon`` spell-resolution variant with creature and source."""

    type: Literal["summon"]
    creature: str
    source: str | None = None
    count: PositiveInt | Literal["spellcasting_modifier"] = 1
    team: Literal["source", "hostile"] = "source"
    initiative: Literal["own", "source_after"] = "source_after"
    command: Literal["verbal", "mental", "none"] = "verbal"


class ReplaceWithCreatureEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``replace_with_creature`` spell-resolution variant with creature."""

    type: Literal["replace_with_creature"]
    creature: str
    source: str | None = None
    position: Literal["target", "nearest_free_space"] = "target"
    team: Literal["source", "target", "hostile"] = "source"


class ExtraActionEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``extra_action`` spell-resolution variant with allowed actions."""

    type: Literal["extra_action"]
    allowed_actions: list[str] = Field(min_length=1)
    attack_limit: PositiveInt | None = None
    duration: EffectDurationSchema | None = None


class ExtraTurnsEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``extra_turns`` spell-resolution variant with count dice and count."""

    type: Literal["extra_turns"]
    count_dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    count: PositiveInt | None = None
    consecutive: bool = True

    @model_validator(mode="after")
    def validate_count(self) -> ExtraTurnsEffectSchema:
        """Require exactly one fixed or rolled extra-turn count.

        >>> ExtraTurnsEffectSchema(type="extra_turns", count=2).count
        2
        >>> from pydantic import ValidationError
        >>> try:
        ...     ExtraTurnsEffectSchema(type="extra_turns", count=2, count_dice="1d4")
        ... except ValidationError as error:
        ...     "exactly one count source" in str(error)
        True
        """
        if (self.count_dice is None) == (self.count is None):
            raise ValueError("Extra turns require exactly one count source.")
        return self


class PreventDefeatEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``prevent_defeat`` spell-resolution variant."""

    type: Literal["prevent_defeat"]
    prevent_drop_to_zero: bool = True
    prevent_instant_death: bool = True
    replacement_hit_points: PositiveInt = 1
    uses: PositiveInt = 1
    duration: EffectDurationSchema | None = None


class SuppressMagicEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``suppress_magic`` spell-resolution variant with minimum spell level."""

    type: Literal["suppress_magic"]
    minimum_spell_level: NonNegativeInt = 0
    exceptions: list[str] = Field(default_factory=list)


class TransformEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``transform`` spell-resolution variant with forms and maximum rating."""

    type: Literal["transform"]
    forms: Literal["beast", "creature_catalog", "authored"]
    maximum_rating: Literal["target_level_or_cr", "cast_level"]
    statistics: Literal["replace", "overlay"] = "replace"
    equipment: Literal["merge", "drop", "retain"] = "merge"


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


class AbilityCheckResolutionSchema(SpellCapabilitySchemaModel):
    """Encode the ``ability_check`` spell-resolution variant with ability and dc."""

    type: Literal["ability_check"]
    ability: Ability | Literal["spellcasting"]
    dc: PositiveInt | Literal["spell_save_dc", "ten_plus_spell_level"]
    success: OutcomeSchema
    failure: OutcomeSchema = Field(default_factory=OutcomeSchema)


class ContestedCheckResolutionSchema(SpellCapabilitySchemaModel):
    """Encode the ``contested_check`` spell-resolution variant with source ability."""

    type: Literal["contested_check"]
    source_ability: Ability | Literal["spellcasting"]
    target_abilities: list[Ability] = Field(min_length=1)
    target_chooses_ability: bool = False
    tie: Literal["source", "target", "no_change"] = "no_change"
    source_wins: OutcomeSchema
    target_wins: OutcomeSchema = Field(default_factory=OutcomeSchema)


class HitPointPoolResolutionSchema(SpellCapabilitySchemaModel):
    """Encode the ``hit_point_pool`` spell-resolution variant with dice and bonus."""

    type: Literal["hit_point_pool"]
    dice: str = Field(pattern=r"^\d+d\d+$")
    bonus: int = 0
    order: Literal["ascending_current_hit_points", "closest_first", "source_choice"] = (
        "ascending_current_hit_points"
    )
    cost: Literal["current_hit_points", "maximum_hit_points"] = "current_hit_points"
    on_covered: OutcomeSchema
    stop_when_next_target_exceeds_pool: bool = False


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


class GrantedActionSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-resolution fields with id and label."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    economy: Literal["action", "bonus_action", "reaction", "magic_action"]
    target: SpellTargetSchema
    resolution: SpellResolutionSchema
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)
    target_history: Literal[
        "none", "exclude_successful_save", "exclude_any_previous_target"
    ] = "none"


class AreaTriggerSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-resolution fields with event and resolution."""

    event: Literal[
        "created",
        "creature_enters",
        "area_enters_creature_space",
        "creature_turn_start",
        "creature_turn_end",
    ]
    resolution: SpellResolutionSchema
    per_target_limit: PositiveInt | None = None
    limit_period: Literal["turn", "round", "spell_instance"] | None = None


class AreaMovementSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-resolution fields with trigger and distance feet."""

    trigger: Literal["source_turn_start", "source_turn_end", "granted_action"]
    distance_feet: PositiveInt
    direction: Literal["away_from_source", "chosen", "fixed"]
    movement_mode: Literal["ground", "flying", "unrestricted"] = "unrestricted"


RepeatResolutionSchema.model_rebuild()
SequenceResolutionSchema.model_rebuild()
RepeatSaveProgressionSchema.model_rebuild()
