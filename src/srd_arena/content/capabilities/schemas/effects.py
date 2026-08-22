"""Authored effect schemas for executable capabilities."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import Ability, CapabilitySchemaModel, NonNegativeInt, PositiveInt
from .durations import EffectDurationSchema
from .requirements import (
    CapabilityRequirementSchema,
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


class HealingEffectSchema(CapabilitySchemaModel):
    type: Literal["healing"]
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    bonus: int = 0
    modifier: Literal["none", "ability_modifier", "spellcasting_ability"] = "none"
    from_damage: Literal["none", "half_damage_dealt", "all_damage_dealt"] = "none"
    restore_to_maximum: bool = False
    pool: PositiveInt | None = None

    @model_validator(mode="after")
    def validate_healing_source(self) -> "HealingEffectSchema":
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


class TemporaryHitPointsEffectSchema(CapabilitySchemaModel):
    type: Literal["temporary_hit_points"]
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    value: NonNegativeInt = 0
    modifier: Literal["none", "ability_modifier", "spellcasting_ability"] = "none"
    trigger: Literal["application", "target_turn_start"] = "application"

    @model_validator(mode="after")
    def validate_temporary_hit_points(self) -> "TemporaryHitPointsEffectSchema":
        if self.dice is None and self.value == 0 and self.modifier == "none":
            raise ValueError("Temporary hit points require a roll, value, or modifier.")
        return self


class ArmorClassModifierEffectSchema(CapabilitySchemaModel):
    type: Literal["armor_class_modifier"]
    value: int
    duration: EffectDurationSchema | None = None


class RemoveEffectSchema(CapabilitySchemaModel):
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


class DamageResistanceEffectSchema(CapabilitySchemaModel):
    type: Literal["damage_resistance"]
    damage_types: list[str] = Field(min_length=1)
    selection: Literal["all", "choose_one"] = "all"
    duration: EffectDurationSchema | None = None


class DamageReductionEffectSchema(CapabilitySchemaModel):
    type: Literal["damage_reduction"]
    damage_types: list[str] = Field(min_length=1)
    selection: Literal["all", "choose_one"] = "all"
    dice: str = Field(pattern=r"^\d+d\d+$")
    limit: PositiveInt = 1
    period: Literal["turn"] = "turn"
    duration: EffectDurationSchema | None = None


class SpeedModifierEffectSchema(CapabilitySchemaModel):
    type: Literal["speed_modifier"]
    feet: int
    duration: EffectDurationSchema | None = None


class ConditionSaveAdvantageEffectSchema(CapabilitySchemaModel):
    type: Literal["condition_save_advantage"]
    conditions: list[str] = Field(min_length=1)
    duration: EffectDurationSchema | None = None


class DamageImmunityEffectSchema(CapabilitySchemaModel):
    type: Literal["damage_immunity"]
    damage_types: list[str] = Field(min_length=1)
    duration: EffectDurationSchema | None = None


class ConditionImmunityEffectSchema(CapabilitySchemaModel):
    type: Literal["condition_immunity"]
    conditions: list[str] = Field(min_length=1)
    suppress_existing: bool = False
    duration: EffectDurationSchema | None = None


class SenseEffectSchema(CapabilitySchemaModel):
    type: Literal["sense"]
    sense: Literal["blindsight", "darkvision", "truesight"]
    range_feet: PositiveInt
    duration: EffectDurationSchema | None = None


class HitPointMaximumModifierEffectSchema(CapabilitySchemaModel):
    type: Literal["hit_point_maximum_modifier"]
    value: int
    also_modify_current: bool = False
    duration: EffectDurationSchema | None = None


class ConditionEffectSchema(CapabilitySchemaModel):
    type: Literal["condition"]
    condition: str = Field(min_length=1)
    duration: EffectDurationSchema | None = None
    requirements: list[CapabilityRequirementSchema] = Field(default_factory=list)
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
    ignored_by_senses: list[Literal["blindsight", "darkvision", "truesight"]] = Field(
        default_factory=list
    )
    ability: Ability | None = None
    ability_options: list[Ability] = Field(default_factory=list)
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    value: int | None = None
    duration: EffectDurationSchema | None = None
    requirements: list[CapabilityRequirementSchema] = Field(default_factory=list)


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


class AttackLimitEffectSchema(CapabilitySchemaModel):
    type: Literal["attack_action_limit"]
    maximum: PositiveInt
    duration: EffectDurationSchema | None = None


class ActionFailureChanceEffectSchema(CapabilitySchemaModel):
    type: Literal["action_failure_chance"]
    action: Literal["cast_spell", "attack", "magic_action", "any"]
    percent: Annotated[int, Field(ge=1, le=100)]
    requirements: list[CapabilityRequirementSchema] = Field(default_factory=list)
    duration: EffectDurationSchema | None = None


class TeleportEffectSchema(CapabilitySchemaModel):
    type: Literal["teleport"]
    distance_feet: NonNegativeInt | Literal["spell_range", "unlimited"]
    destination: Literal[
        "chosen_space", "origin_space", "nearest_free_space", "another_plane"
    ]


class ObscurementEffectSchema(CapabilitySchemaModel):
    type: Literal["obscurement"]
    degree: Literal["light", "heavy"]


class MovementModeEffectSchema(CapabilitySchemaModel):
    type: Literal["movement_mode"]
    mode: Literal["walk", "fly", "swim", "climb", "burrow", "hover"]
    speed_feet: PositiveInt | Literal["walking_speed"]
    duration: EffectDurationSchema | None = None


class DifficultTerrainEffectSchema(CapabilitySchemaModel):
    type: Literal["difficult_terrain"]
    applies_to: Literal["all", "enemies", "creatures_on_ground"] = "all"


class BattlefieldRemovalEffectSchema(CapabilitySchemaModel):
    type: Literal["battlefield_removal"]
    destination: Literal["demiplane", "another_plane", "extradimensional", "off_board"]
    return_trigger: Literal["spell_ends", "turn_start", "turn_end", "random_turn_start"]
    return_position: Literal["origin", "nearest_free_space", "chosen_free_space"]


class RelationshipEffectSchema(CapabilitySchemaModel):
    type: Literal["relationship"]
    relationship: str = Field(min_length=1)
    source_role: str = Field(default="source", min_length=1)
    target_role: str = Field(default="target", min_length=1)
    unique: Literal["none", "per_source", "per_target", "per_pair"] = "per_pair"


class MirroredDamageEffectSchema(CapabilitySchemaModel):
    type: Literal["mirrored_damage"]
    from_event: Literal["triggering_damage"] = "triggering_damage"
    numerator: PositiveInt = 1
    denominator: PositiveInt = 1
    damage_type: Literal["same", "force"] = "same"
    prevent_recursion: bool = True


class CompelledBehaviorEffectSchema(CapabilitySchemaModel):
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


class CancelPendingEventEffectSchema(CapabilitySchemaModel):
    type: Literal["cancel_pending_event"]
    event: Literal["attack", "damage", "spell", "defeat", "instant_death"]
    consume_triggering_resources: bool = True


class RedirectPendingTargetEffectSchema(CapabilitySchemaModel):
    type: Literal["redirect_pending_target"]
    destination: Literal["random_spell_entity", "chosen_legal_target"]


class RequireTargetReselectionEffectSchema(CapabilitySchemaModel):
    type: Literal["require_target_reselection"]
    on_no_legal_target: Literal["cancel_action", "retain_target"] = "cancel_action"


class LightEffectSchema(CapabilitySchemaModel):
    type: Literal["light"]
    bright_radius_feet: NonNegativeInt = 0
    dim_additional_feet: NonNegativeInt = 0


class CreatedEntityStatisticsSchema(CapabilitySchemaModel):
    armor_class: PositiveInt | Literal["caster"] | None = None
    hit_points: PositiveInt | Literal["caster_maximum"] | None = None
    size: str | None = None
    ability_scores: dict[Ability, Annotated[int, Field(ge=1, le=30)]] = Field(
        default_factory=dict
    )
    condition_immunities: list[str] = Field(default_factory=list)
    damage_immunities: list[str] = Field(default_factory=list)


class TransformObjectEffectSchema(CapabilitySchemaModel):
    type: Literal["transform_object"]
    creature_by_size: dict[str, str] = Field(min_length=1)
    restore_object_on_end: bool = True
    carry_damage_to_object: bool = True


class AccumulateDiceEffectSchema(CapabilitySchemaModel):
    type: Literal["accumulate_dice"]
    counter: str = Field(min_length=1)
    dice: str = Field(pattern=r"^\d+d\d+$")
    maximum_dice: PositiveInt | None = None


class AccumulatedDamageEffectSchema(CapabilitySchemaModel):
    type: Literal["accumulated_damage"]
    base_dice: str = Field(pattern=r"^\d+d\d+$")
    counter: str = Field(min_length=1)
    dice_per_counter: str = Field(pattern=r"^\d+d\d+$")
    damage_type: str = Field(min_length=1)


class SummonEffectSchema(CapabilitySchemaModel):
    type: Literal["summon"]
    creature: str
    source: str | None = None
    count: PositiveInt | Literal["spellcasting_modifier"] = 1
    team: Literal["source", "hostile"] = "source"
    initiative: Literal["own", "source_after"] = "source_after"
    command: Literal["verbal", "mental", "none"] = "verbal"


class ReplaceWithCreatureEffectSchema(CapabilitySchemaModel):
    type: Literal["replace_with_creature"]
    creature: str
    source: str | None = None
    position: Literal["target", "nearest_free_space"] = "target"
    team: Literal["source", "target", "hostile"] = "source"


class ExtraActionEffectSchema(CapabilitySchemaModel):
    type: Literal["extra_action"]
    allowed_actions: list[str] = Field(min_length=1)
    attack_limit: PositiveInt | None = None
    duration: EffectDurationSchema | None = None


class ExtraTurnsEffectSchema(CapabilitySchemaModel):
    type: Literal["extra_turns"]
    count_dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    count: PositiveInt | None = None
    consecutive: bool = True

    @model_validator(mode="after")
    def validate_count(self) -> "ExtraTurnsEffectSchema":
        if (self.count_dice is None) == (self.count is None):
            raise ValueError("Extra turns require exactly one count source.")
        return self


class PreventDefeatEffectSchema(CapabilitySchemaModel):
    type: Literal["prevent_defeat"]
    prevent_drop_to_zero: bool = True
    prevent_instant_death: bool = True
    replacement_hit_points: PositiveInt = 1
    uses: PositiveInt = 1
    duration: EffectDurationSchema | None = None


class SuppressMagicEffectSchema(CapabilitySchemaModel):
    type: Literal["suppress_magic"]
    minimum_spell_level: NonNegativeInt = 0
    exceptions: list[str] = Field(default_factory=list)


class TransformEffectSchema(CapabilitySchemaModel):
    type: Literal["transform"]
    forms: Literal["beast", "creature_catalog", "authored"]
    maximum_rating: Literal["target_level_or_cr", "cast_level"]
    statistics: Literal["replace", "overlay"] = "replace"
    equipment: Literal["merge", "drop", "retain"] = "merge"


ActionEffectSchema = Annotated[
    DamageEffectSchema
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
    | HitPointMaximumModifierEffectSchema
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
