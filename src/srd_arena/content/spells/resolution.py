"""Validate spell outcomes that require spell-specific authoring fields."""

from __future__ import annotations

from collections.abc import Sequence
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
from .implementation import SpellImplementationSchema
from .targeting import (
    AreaGeometrySchema,
    EventSpellTargetSchema,
    SpellRequirementSchema,
    SpellSaveModifierSchema,
    SpellTargetSchema,
)


def _validate_complete_roll_table(
    die: str,
    entries: Sequence[RandomResolutionEntrySchema | RandomTableEntrySchema],
) -> None:
    count_text, sides_text = die.lower().split("d", 1)
    expected = int(count_text)
    maximum = int(count_text) * int(sides_text)
    for entry in sorted(entries, key=lambda candidate: candidate.minimum):
        if entry.minimum != expected:
            raise ValueError(
                "Random-table ranges must be contiguous and non-overlapping."
            )
        expected = entry.maximum + 1
    if expected != maximum + 1:
        raise ValueError("Random-table ranges must cover every possible roll.")


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


class AttackLimitEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``attack_action_limit`` spell-resolution variant with maximum."""

    type: Literal["attack_action_limit"]
    maximum: PositiveInt
    duration: EffectDurationSchema | None = None


class ActionFailureChanceEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``action_failure_chance`` spell-resolution variant with action."""

    type: Literal["action_failure_chance"]
    action: Literal["cast_spell", "attack", "magic_action", "any"]
    percent: Annotated[int, Field(ge=1, le=100)]
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)
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


class TeleportEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``teleport`` spell-resolution variant with distance feet."""

    type: Literal["teleport"]
    distance_feet: NonNegativeInt | Literal["spell_range", "unlimited"]
    destination: Literal[
        "chosen_space", "origin_space", "nearest_free_space", "another_plane"
    ]


class ObscurementEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``obscurement`` spell-resolution variant with degree."""

    type: Literal["obscurement"]
    degree: Literal["light", "heavy"]


class MovementModeEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``movement_mode`` spell-resolution variant with mode and speed feet."""

    type: Literal["movement_mode"]
    mode: Literal["walk", "fly", "swim", "climb", "burrow", "hover"]
    speed_feet: PositiveInt | Literal["walking_speed"]
    duration: EffectDurationSchema | None = None


class DifficultTerrainEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``difficult_terrain`` spell-resolution variant with applies to."""

    type: Literal["difficult_terrain"]
    applies_to: Literal["all", "enemies", "creatures_on_ground"] = "all"


class BattlefieldRemovalEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``battlefield_removal`` spell-resolution variant with destination."""

    type: Literal["battlefield_removal"]
    destination: Literal["demiplane", "another_plane", "extradimensional", "off_board"]
    return_trigger: Literal["spell_ends", "turn_start", "turn_end", "random_turn_start"]
    return_position: Literal["origin", "nearest_free_space", "chosen_free_space"]


class RelationshipEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``relationship`` spell-resolution variant with relationship."""

    type: Literal["relationship"]
    relationship: str = Field(min_length=1)
    source_role: str = Field(default="source", min_length=1)
    target_role: str = Field(default="target", min_length=1)
    unique: Literal["none", "per_source", "per_target", "per_pair"] = "per_pair"


class MirroredDamageEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``mirrored_damage`` spell-resolution variant with from event."""

    type: Literal["mirrored_damage"]
    from_event: Literal["triggering_damage"] = "triggering_damage"
    numerator: PositiveInt = 1
    denominator: PositiveInt = 1
    damage_type: Literal["same", "force"] = "same"
    prevent_recursion: bool = True


class CompelledBehaviorEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``compelled_behavior`` spell-resolution variant with behavior."""

    type: Literal["compelled_behavior"]
    behavior: Literal[
        "authored_command",
        "approach_source",
        "flee_source",
        "drop_prone",
        "end_turn",
        "controller_selected",
    ]
    decision_provider: Literal["source_controller", "rules_engine"] = "rules_engine"
    command_id: str | None = None


class CancelPendingEventEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``cancel_pending_event`` spell-resolution variant with event."""

    type: Literal["cancel_pending_event"]
    event: Literal["attack", "damage", "spell", "defeat", "instant_death"]
    consume_triggering_resources: bool = True


class RedirectPendingTargetEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``redirect_pending_target`` spell-resolution variant."""

    type: Literal["redirect_pending_target"]
    destination: Literal["random_spell_entity", "chosen_legal_target"]


class RequireTargetReselectionEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``require_target_reselection`` spell-resolution variant."""

    type: Literal["require_target_reselection"]
    on_no_legal_target: Literal["cancel_action", "retain_target"] = "cancel_action"


class LightEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``light`` spell-resolution variant with bright radius feet."""

    type: Literal["light"]
    bright_radius_feet: NonNegativeInt = 0
    dim_additional_feet: NonNegativeInt = 0


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


class CreateSpellEntityEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``create_spell_entity`` spell-resolution variant with entity id."""

    type: Literal["create_spell_entity"]
    entity_id: str = Field(min_length=1)
    entity_kind: Literal["manifestation", "weapon", "hand", "hazard", "image"]
    targetable: bool = False
    occupies_space: bool = False
    geometry: AreaGeometrySchema | None = None
    statistics: SpellEntityStatisticsSchema | None = None
    movement: AreaMovementSchema | None = None
    actions: list[GrantedActionSchema] = Field(default_factory=list)


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


class StoreSpellEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``store_spell`` spell-resolution variant with maximum level."""

    type: Literal["store_spell"]
    maximum_level: NonNegativeInt | Literal["cast_level"]
    activation_trigger: Literal[
        "creature_enters_area",
        "object_opened",
        "object_touched",
        "spell_cast_nearby",
        "source_turn_start",
        "source_turn_end",
    ]
    activation_target: EventSpellTargetSchema | None = None
    inherit_casting_statistics: bool = True
    spell_name: str | None = None
    spell_source: str | None = None
    stored_resolution: SpellResolutionSchema | None = None

    @model_validator(mode="after")
    def validate_stored_payload(self) -> StoreSpellEffectSchema:
        """Require exactly one referenced spell or authored resolution.

        >>> stored = StoreSpellEffectSchema(type="store_spell", maximum_level=3,
        ...     activation_trigger="object_touched", spell_name="Fireball")
        >>> stored.spell_name
        'Fireball'
        >>> from pydantic import ValidationError
        >>> try:
        ...     StoreSpellEffectSchema(type="store_spell", maximum_level=3,
        ...         activation_trigger="object_touched")
        ... except ValidationError as error:
        ...     "exactly one" in str(error)
        True
        """
        if (self.spell_name is None) == (self.stored_resolution is None):
            raise ValueError(
                "Stored spell effects require exactly one spell or authored resolution."
            )
        return self


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


class CreatePersistentAreaEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``create_persistent_area`` spell-resolution variant."""

    type: Literal["create_persistent_area"]
    geometry_from_target: bool = True
    properties: list[PersistentAreaPropertySchema] = Field(default_factory=list)
    triggers: list[AreaTriggerSchema] = Field(default_factory=list)
    movement: AreaMovementSchema | None = None
    hazardous_side: Literal["none", "chosen"] = "none"
    ends_on: list[
        Literal[
            "strong_wind",
            "source_dies",
            "source_incapacitated",
            "source_loses_concentration",
            "parent_spell_ends",
        ]
    ] = Field(default_factory=list)


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


class RandomOutcomeEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``random_outcome`` spell-resolution variant with table."""

    type: Literal["random_outcome"]
    table: RandomTableSchema


class OngoingModifierGroupEffectSchema(SpellCapabilitySchemaModel):
    """Encode the ``ongoing_modifier_group`` spell-resolution variant with duration."""

    type: Literal["ongoing_modifier_group"]
    duration: EffectDurationSchema | None = None
    modifiers: list[OngoingModifierSchema] = Field(min_length=1)


PersistentAreaPropertySchema = Annotated[
    ObscurementEffectSchema
    | LightEffectSchema
    | DifficultTerrainEffectSchema
    | SuppressMagicEffectSchema,
    Field(discriminator="type"),
]


OngoingModifierSchema = Annotated[
    SpeedMultiplierEffectSchema
    | ProhibitReactionEffectSchema
    | TurnEconomyRestrictionEffectSchema
    | RollModifierEffectSchema
    | ArmorClassModifierEffectSchema
    | AttackLimitEffectSchema
    | ActionFailureChanceEffectSchema
    | DamageResistanceEffectSchema
    | DamageReductionEffectSchema
    | SpeedModifierEffectSchema
    | ConditionSaveAdvantageEffectSchema
    | DamageImmunityEffectSchema
    | ConditionImmunityEffectSchema
    | SenseEffectSchema
    | MovementModeEffectSchema
    | ExtraActionEffectSchema,
    Field(discriminator="type"),
]


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
            | AttackLimitEffectSchema
            | ActionFailureChanceEffectSchema
            | RemoveEffectSchema
            | DamageResistanceEffectSchema
            | DamageReductionEffectSchema
            | SpeedModifierEffectSchema
            | ConditionSaveAdvantageEffectSchema
            | DamageImmunityEffectSchema
            | ConditionImmunityEffectSchema
            | SenseEffectSchema
            | HitPointMaximumModifierEffectSchema
            | TeleportEffectSchema
            | ObscurementEffectSchema
            | MovementModeEffectSchema
            | DifficultTerrainEffectSchema
            | BattlefieldRemovalEffectSchema
            | RelationshipEffectSchema
            | MirroredDamageEffectSchema
            | CompelledBehaviorEffectSchema
            | CancelPendingEventEffectSchema
            | RedirectPendingTargetEffectSchema
            | RequireTargetReselectionEffectSchema
            | LightEffectSchema
            | CreateSpellEntityEffectSchema
            | TransformObjectEffectSchema
            | AccumulateDiceEffectSchema
            | AccumulatedDamageEffectSchema
            | StoreSpellEffectSchema
            | GrantActionEffectSchema
            | CreatePersistentAreaEffectSchema
            | SummonEffectSchema
            | ReplaceWithCreatureEffectSchema
            | ExtraActionEffectSchema
            | ExtraTurnsEffectSchema
            | PreventDefeatEffectSchema
            | SuppressMagicEffectSchema
            | TransformEffectSchema
            | RandomOutcomeEffectSchema
            | OngoingModifierGroupEffectSchema,
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


class ResolutionChoiceOptionSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-resolution fields with id and label."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    resolution: SpellResolutionSchema
    implementation: SpellImplementationSchema | None = None


class ChoiceResolutionSchema(SpellCapabilitySchemaModel):
    """Encode the ``choice`` spell-resolution variant with count and options."""

    type: Literal["choice"]
    count: PositiveInt = 1
    options: list[ResolutionChoiceOptionSchema] = Field(min_length=1)


class RandomResolutionEntrySchema(SpellCapabilitySchemaModel):
    """Define the authored spell-resolution fields with minimum and maximum."""

    minimum: PositiveInt
    maximum: PositiveInt
    resolution: SpellResolutionSchema

    @model_validator(mode="after")
    def validate_range(self) -> RandomResolutionEntrySchema:
        """Reject a random-resolution range whose minimum exceeds its maximum.

        >>> from pydantic import ValidationError
        >>> try:
        ...     RandomResolutionEntrySchema(minimum=2, maximum=1,
        ...         resolution={"type": "automatic", "outcome": {}})
        ... except ValidationError as error:
        ...     "minimum cannot exceed maximum" in str(error)
        True
        """
        if self.minimum > self.maximum:
            raise ValueError("Random result minimum cannot exceed maximum.")
        return self


class RandomTableResolutionSchema(SpellCapabilitySchemaModel):
    """Encode the ``random_table`` spell-resolution variant with die and per target."""

    type: Literal["random_table"]
    die: str = Field(pattern=r"^\d+d\d+$")
    per_target: bool = False
    entries: list[RandomResolutionEntrySchema] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_entries(self) -> RandomTableResolutionSchema:
        """Require contiguous entries covering every result on the table die.

        >>> automatic = {"type": "automatic", "outcome": {}}
        >>> table = RandomTableResolutionSchema(type="random_table", die="1d2", entries=[
        ...     {"minimum": 1, "maximum": 1, "resolution": automatic},
        ...     {"minimum": 2, "maximum": 2, "resolution": automatic},
        ... ])
        >>> len(table.entries)
        2
        """
        _validate_complete_roll_table(self.die, self.entries)
        return self


class SpellResolutionSchema(
    RootModel[
        Annotated[
            AutomaticResolutionSchema
            | SavingThrowResolutionSchema
            | SpellAttackResolutionSchema
            | AbilityCheckResolutionSchema
            | ContestedCheckResolutionSchema
            | HitPointPoolResolutionSchema
            | RepeatResolutionSchema
            | SequenceResolutionSchema
            | ChoiceResolutionSchema
            | RandomTableResolutionSchema,
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


class RandomTableEntrySchema(SpellCapabilitySchemaModel):
    """Define the authored spell-resolution fields with minimum and maximum."""

    minimum: PositiveInt
    maximum: PositiveInt
    resolution: SpellResolutionSchema

    @model_validator(mode="after")
    def validate_range(self) -> RandomTableEntrySchema:
        """Reject a random-effect range whose minimum exceeds its maximum.

        >>> from pydantic import ValidationError
        >>> try:
        ...     RandomTableEntrySchema(minimum=2, maximum=1,
        ...         resolution={"type": "automatic", "outcome": {}})
        ... except ValidationError as error:
        ...     "minimum cannot exceed maximum" in str(error)
        True
        """
        if self.minimum > self.maximum:
            raise ValueError("Random result minimum cannot exceed maximum.")
        return self


class RandomTableSchema(SpellCapabilitySchemaModel):
    """Define the authored spell-resolution fields with die and entries."""

    die: str = Field(pattern=r"^\d+d\d+$")
    entries: list[RandomTableEntrySchema] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_entries(self) -> RandomTableSchema:
        """Require contiguous effect entries covering every die result.

        >>> automatic = {"type": "automatic", "outcome": {}}
        >>> table = RandomTableSchema(die="1d2", entries=[
        ...     {"minimum": 1, "maximum": 1, "resolution": automatic},
        ...     {"minimum": 2, "maximum": 2, "resolution": automatic},
        ... ])
        >>> len(table.entries)
        2
        """
        _validate_complete_roll_table(self.die, self.entries)
        return self


GrantActionEffectSchema.model_rebuild()
CreatePersistentAreaEffectSchema.model_rebuild()
CreateSpellEntityEffectSchema.model_rebuild()
StoreSpellEffectSchema.model_rebuild()
RandomOutcomeEffectSchema.model_rebuild()
RepeatResolutionSchema.model_rebuild()
SequenceResolutionSchema.model_rebuild()
ResolutionChoiceOptionSchema.model_rebuild()
ChoiceResolutionSchema.model_rebuild()
RandomResolutionEntrySchema.model_rebuild()
RandomTableResolutionSchema.model_rebuild()
RepeatSaveProgressionSchema.model_rebuild()
GrantedActionSchema.model_rebuild()
AreaTriggerSchema.model_rebuild()
RandomTableEntrySchema.model_rebuild()
RandomTableSchema.model_rebuild()
