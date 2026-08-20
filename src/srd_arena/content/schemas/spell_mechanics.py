from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from .action_mechanics import (
    Ability,
    ConditionEffectSchema,
    ConditionRequirementSchema,
    CreatureTypeRequirementSchema,
    DamageEffectSchema,
    EffectDurationSchema,
    ForcedMovementEffectSchema,
    NonNegativeInt,
    NotAffectedRequirementSchema,
    PositiveInt,
    ProhibitReactionEffectSchema,
    RollModifierEffectSchema,
    SizeRequirementSchema,
    SpeedMultiplierEffectSchema,
    TurnEconomyRestrictionEffectSchema,
)


class SpellMechanicsSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_complete_roll_table(
    die: str,
    entries: Sequence[RandomResolutionEntrySchema | RandomTableEntrySchema],
) -> None:
    count_text, sides_text = die.lower().split("d", 1)
    expected = int(count_text)
    maximum = int(count_text) * int(sides_text)
    for entry in sorted(entries, key=lambda candidate: candidate.minimum):
        if entry.minimum != expected:
            raise ValueError("Random-table ranges must be contiguous and non-overlapping.")
        expected = entry.maximum + 1
    if expected != maximum + 1:
        raise ValueError("Random-table ranges must cover every possible roll.")


ImplementationScope = Literal["combat", "exploration", "social", "world"]


def _default_implementation_scope() -> list[ImplementationScope]:
    return ["combat"]


class ImplementationOmissionSchema(SpellMechanicsSchemaModel):
    mechanic: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class SpellImplementationSchema(SpellMechanicsSchemaModel):
    status: Literal[
        "complete",
        "partial",
        "unimplemented",
        "blocked",
        "out_of_scope",
    ] = "unimplemented"
    scope: list[ImplementationScope] = Field(
        default_factory=_default_implementation_scope
    )
    omissions: list[ImplementationOmissionSchema] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    reason: str | None = None

    @model_validator(mode="after")
    def validate_status_details(self) -> "SpellImplementationSchema":
        if self.status == "partial" and not self.omissions:
            raise ValueError("Partial spell implementations must list omissions.")
        if self.status == "blocked" and not self.blocked_by:
            raise ValueError("Blocked spell implementations must list blockers.")
        if self.status == "out_of_scope" and not self.reason:
            raise ValueError("Out-of-scope spells must provide a reason.")
        if self.status == "complete" and (self.omissions or self.blocked_by):
            raise ValueError("Complete spell implementations cannot have omissions.")
        return self


class CreatureTraitRequirementSchema(SpellMechanicsSchemaModel):
    type: Literal["creature_trait"]
    trait: str = Field(min_length=1)


class ConditionImmunityRequirementSchema(SpellMechanicsSchemaModel):
    type: Literal["condition_immunity"]
    condition: str = Field(min_length=1)


class SpellComponentRequirementSchema(SpellMechanicsSchemaModel):
    type: Literal["spell_component"]
    component: Literal["verbal", "somatic", "material"]


class AttackSourceRequirementSchema(SpellMechanicsSchemaModel):
    type: Literal["attack_source"]
    source: Literal["weapon", "unarmed_strike", "spell", "any"]
    mode: Literal["melee", "ranged", "any"] = "any"


class WillingRequirementSchema(SpellMechanicsSchemaModel):
    type: Literal["willing"]


class FreeHandRequirementSchema(SpellMechanicsSchemaModel):
    type: Literal["free_hand"]


class PerceptionRequirementSchema(SpellMechanicsSchemaModel):
    type: Literal["perception"]
    sense: Literal["see", "hear"]
    subject: Literal["source", "target", "each_other"] = "source"


class HitPointRequirementSchema(SpellMechanicsSchemaModel):
    type: Literal["hit_points"]
    comparison: Literal["less_than", "at_most", "at_least", "greater_than"]
    value: NonNegativeInt


class RelationshipRequirementSchema(SpellMechanicsSchemaModel):
    type: Literal["relationship"]
    relationship: str = Field(min_length=1)
    established_by: Literal["this_spell", "source", "any"] = "any"


class AnyRequirementSchema(SpellMechanicsSchemaModel):
    type: Literal["any"]
    requirements: list[SpellRequirementSchema] = Field(min_length=1)


class AllRequirementSchema(SpellMechanicsSchemaModel):
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


class SpellSaveModifierSchema(SpellMechanicsSchemaModel):
    type: Literal["roll_modifier"]
    roll: Literal["saving_throw"]
    mode: Literal["advantage", "disadvantage", "add", "subtract"]
    ability: Ability | None = None
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    value: int | None = None
    duration: EffectDurationSchema | None = None
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)


class TargetCountSchema(SpellMechanicsSchemaModel):
    minimum: NonNegativeInt = 1
    maximum: PositiveInt | Literal["spellcasting_modifier", "all"] = 1

    @model_validator(mode="after")
    def validate_bounds(self) -> "TargetCountSchema":
        if isinstance(self.maximum, int) and self.minimum > self.maximum:
            raise ValueError("Target count minimum cannot exceed maximum.")
        return self


class SelfSpellTargetSchema(SpellMechanicsSchemaModel):
    type: Literal["self"]


class CreatureSpellTargetSchema(SpellMechanicsSchemaModel):
    type: Literal["creature"]
    count: TargetCountSchema = Field(default_factory=TargetCountSchema)
    disposition: Literal[
        "any", "ally", "enemy", "willing", "source", "trigger_target"
    ] = "any"
    selection: Literal["all", "choose", "choose_up_to"] = "choose"
    line_of_sight: bool = False
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)


class ObjectSpellTargetSchema(SpellMechanicsSchemaModel):
    type: Literal["object"]
    count: TargetCountSchema = Field(default_factory=TargetCountSchema)
    carried: Literal["allowed", "required", "forbidden"] = "allowed"
    worn: Literal["allowed", "required", "forbidden"] = "allowed"
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)


class PointSpellTargetSchema(SpellMechanicsSchemaModel):
    type: Literal["point"]
    surface: Literal["any", "solid", "ground"] = "any"
    line_of_sight: bool = False


class EventSpellTargetSchema(SpellMechanicsSchemaModel):
    type: Literal["event_target"]
    binding: Literal[
        "triggering_actor",
        "triggering_target",
        "triggering_attacker",
        "triggering_caster",
        "effect_source",
        "effect_target",
    ]


class AreaGeometrySchema(SpellMechanicsSchemaModel):
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


class AreaSpellTargetSchema(SpellMechanicsSchemaModel):
    type: Literal["area"]
    origin: Literal[
        "self", "point_in_range", "target", "spell_entity", "event_target"
    ]
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


class CompositeAreaComponentSchema(SpellMechanicsSchemaModel):
    geometry: AreaGeometrySchema
    minimum: PositiveInt = 1
    maximum: PositiveInt

    @model_validator(mode="after")
    def validate_bounds(self) -> "CompositeAreaComponentSchema":
        if self.minimum > self.maximum:
            raise ValueError("Composite area minimum cannot exceed maximum.")
        return self


class CompositeAreaSpellTargetSchema(SpellMechanicsSchemaModel):
    type: Literal["composite_area"]
    origin: Literal["point_in_range"] = "point_in_range"
    component: CompositeAreaComponentSchema
    contiguity: Literal["none", "edge", "edge_or_corner", "touching_3d"] = "edge"
    require_connected_set: bool = True
    overlap: Literal["forbidden", "union"] = "union"
    occupants: Literal["all", "allies", "enemies", "chosen"] = "all"


class SpellEntityTargetSchema(SpellMechanicsSchemaModel):
    type: Literal["spell_entity"]
    ownership: Literal["source", "any"] = "source"
    entity_kinds: list[str] = Field(default_factory=list)


class TargetChoiceOptionSchema(SpellMechanicsSchemaModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    target: SpellTargetSchema


class ChoiceSpellTargetSchema(SpellMechanicsSchemaModel):
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


class HealingEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["healing"]
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    bonus: int = 0
    modifier: Literal["none", "spellcasting_ability"] = "none"
    from_damage: Literal["none", "half_damage_dealt", "all_damage_dealt"] = "none"

    @model_validator(mode="after")
    def validate_healing_source(self) -> "HealingEffectSchema":
        if (
            self.dice is None
            and self.bonus == 0
            and self.modifier == "none"
            and self.from_damage == "none"
        ):
            raise ValueError("Healing requires a roll, value, modifier, or damage source.")
        return self


class TemporaryHitPointsEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["temporary_hit_points"]
    dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    value: NonNegativeInt = 0
    modifier: Literal["none", "spellcasting_ability"] = "none"

    @model_validator(mode="after")
    def validate_temporary_hit_points(self) -> "TemporaryHitPointsEffectSchema":
        if self.dice is None and self.value == 0 and self.modifier == "none":
            raise ValueError("Temporary hit points require a roll, value, or modifier.")
        return self


class ArmorClassModifierEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["armor_class_modifier"]
    value: int
    duration: EffectDurationSchema | None = None


class AttackLimitEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["attack_action_limit"]
    maximum: PositiveInt
    duration: EffectDurationSchema | None = None


class ActionFailureChanceEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["action_failure_chance"]
    action: Literal["cast_spell", "attack", "magic_action", "any"]
    percent: Annotated[int, Field(ge=1, le=100)]
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)
    duration: EffectDurationSchema | None = None


class RemoveEffectSchema(SpellMechanicsSchemaModel):
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


class DamageResistanceEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["damage_resistance"]
    damage_types: list[str] = Field(min_length=1)
    duration: EffectDurationSchema | None = None


class DamageImmunityEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["damage_immunity"]
    damage_types: list[str] = Field(min_length=1)
    duration: EffectDurationSchema | None = None


class ConditionImmunityEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["condition_immunity"]
    conditions: list[str] = Field(min_length=1)
    suppress_existing: bool = False
    duration: EffectDurationSchema | None = None


class HitPointMaximumModifierEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["hit_point_maximum_modifier"]
    value: int
    also_modify_current: bool = False
    duration: EffectDurationSchema | None = None


class TeleportEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["teleport"]
    distance_feet: NonNegativeInt | Literal["spell_range", "unlimited"]
    destination: Literal[
        "chosen_space", "origin_space", "nearest_free_space", "another_plane"
    ]


class ObscurementEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["obscurement"]
    degree: Literal["light", "heavy"]


class MovementModeEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["movement_mode"]
    mode: Literal["walk", "fly", "swim", "climb", "burrow", "hover"]
    speed_feet: PositiveInt | Literal["walking_speed"]
    duration: EffectDurationSchema | None = None


class DifficultTerrainEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["difficult_terrain"]
    applies_to: Literal["all", "enemies", "creatures_on_ground"] = "all"


class BattlefieldRemovalEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["battlefield_removal"]
    destination: Literal["demiplane", "another_plane", "extradimensional", "off_board"]
    return_trigger: Literal[
        "spell_ends", "turn_start", "turn_end", "random_turn_start"
    ]
    return_position: Literal["origin", "nearest_free_space", "chosen_free_space"]


class RelationshipEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["relationship"]
    relationship: str = Field(min_length=1)
    source_role: str = Field(default="source", min_length=1)
    target_role: str = Field(default="target", min_length=1)
    unique: Literal["none", "per_source", "per_target", "per_pair"] = "per_pair"


class MirroredDamageEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["mirrored_damage"]
    from_event: Literal["triggering_damage"] = "triggering_damage"
    numerator: PositiveInt = 1
    denominator: PositiveInt = 1
    damage_type: Literal["same", "force"] = "same"
    prevent_recursion: bool = True


class CompelledBehaviorEffectSchema(SpellMechanicsSchemaModel):
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


class CancelPendingEventEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["cancel_pending_event"]
    event: Literal["attack", "damage", "spell", "defeat", "instant_death"]
    consume_triggering_resources: bool = True


class RedirectPendingTargetEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["redirect_pending_target"]
    destination: Literal["random_spell_entity", "chosen_legal_target"]


class RequireTargetReselectionEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["require_target_reselection"]
    on_no_legal_target: Literal["cancel_action", "retain_target"] = "cancel_action"


class LightEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["light"]
    bright_radius_feet: NonNegativeInt = 0
    dim_additional_feet: NonNegativeInt = 0


class SpellEntityStatisticsSchema(SpellMechanicsSchemaModel):
    armor_class: PositiveInt | Literal["caster"] | None = None
    hit_points: PositiveInt | Literal["caster_maximum"] | None = None
    size: str | None = None
    ability_scores: dict[Ability, Annotated[int, Field(ge=1, le=30)]] = Field(
        default_factory=dict
    )
    condition_immunities: list[str] = Field(default_factory=list)
    damage_immunities: list[str] = Field(default_factory=list)


class CreateSpellEntityEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["create_spell_entity"]
    entity_id: str = Field(min_length=1)
    entity_kind: Literal["manifestation", "weapon", "hand", "hazard", "image"]
    targetable: bool = False
    occupies_space: bool = False
    geometry: AreaGeometrySchema | None = None
    statistics: SpellEntityStatisticsSchema | None = None
    movement: AreaMovementSchema | None = None
    actions: list[GrantedActionSchema] = Field(default_factory=list)


class TransformObjectEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["transform_object"]
    creature_by_size: dict[str, str] = Field(min_length=1)
    restore_object_on_end: bool = True
    carry_damage_to_object: bool = True


class AccumulateDiceEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["accumulate_dice"]
    counter: str = Field(min_length=1)
    dice: str = Field(pattern=r"^\d+d\d+$")
    maximum_dice: PositiveInt | None = None


class StoreSpellEffectSchema(SpellMechanicsSchemaModel):
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
    def validate_stored_payload(self) -> "StoreSpellEffectSchema":
        if (self.spell_name is None) == (self.stored_resolution is None):
            raise ValueError(
                "Stored spell effects require exactly one spell or authored resolution."
            )
        return self


class AccumulatedDamageEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["accumulated_damage"]
    base_dice: str = Field(pattern=r"^\d+d\d+$")
    counter: str = Field(min_length=1)
    dice_per_counter: str = Field(pattern=r"^\d+d\d+$")
    damage_type: str = Field(min_length=1)


class GrantActionEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["grant_action"]
    action: GrantedActionSchema


class CreatePersistentAreaEffectSchema(SpellMechanicsSchemaModel):
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


class SummonEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["summon"]
    creature: str
    source: str | None = None
    count: PositiveInt | Literal["spellcasting_modifier"] = 1
    team: Literal["source", "hostile"] = "source"
    initiative: Literal["own", "source_after"] = "source_after"
    command: Literal["verbal", "mental", "none"] = "verbal"


class ReplaceWithCreatureEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["replace_with_creature"]
    creature: str
    source: str | None = None
    position: Literal["target", "nearest_free_space"] = "target"
    team: Literal["source", "target", "hostile"] = "source"


class ExtraActionEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["extra_action"]
    allowed_actions: list[str] = Field(min_length=1)
    attack_limit: PositiveInt | None = None
    duration: EffectDurationSchema | None = None


class ExtraTurnsEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["extra_turns"]
    count_dice: str | None = Field(default=None, pattern=r"^\d+d\d+$")
    count: PositiveInt | None = None
    consecutive: bool = True

    @model_validator(mode="after")
    def validate_count(self) -> "ExtraTurnsEffectSchema":
        if (self.count_dice is None) == (self.count is None):
            raise ValueError("Extra turns require exactly one count source.")
        return self


class PreventDefeatEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["prevent_defeat"]
    prevent_drop_to_zero: bool = True
    prevent_instant_death: bool = True
    replacement_hit_points: PositiveInt = 1
    uses: PositiveInt = 1
    duration: EffectDurationSchema | None = None


class SuppressMagicEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["suppress_magic"]
    minimum_spell_level: NonNegativeInt = 0
    exceptions: list[str] = Field(default_factory=list)


class TransformEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["transform"]
    forms: Literal["beast", "creature_catalog", "authored"]
    maximum_rating: Literal["target_level_or_cr", "cast_level"]
    statistics: Literal["replace", "overlay"] = "replace"
    equipment: Literal["merge", "drop", "retain"] = "merge"


class RandomOutcomeEffectSchema(SpellMechanicsSchemaModel):
    type: Literal["random_outcome"]
    table: RandomTableSchema


class OngoingModifierGroupEffectSchema(SpellMechanicsSchemaModel):
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
    | DamageImmunityEffectSchema
    | ConditionImmunityEffectSchema
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
            | DamageImmunityEffectSchema
            | ConditionImmunityEffectSchema
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
    pass


class OutcomeSchema(SpellMechanicsSchemaModel):
    effects: list[SpellEffectSchema] = Field(default_factory=list)
    end_spell: bool = False


class AutomaticResolutionSchema(SpellMechanicsSchemaModel):
    type: Literal["automatic"]
    outcome: OutcomeSchema


class SavingThrowResolutionSchema(SpellMechanicsSchemaModel):
    type: Literal["saving_throw"]
    ability: Ability | None = None
    use_spell_metadata_ability: bool = True
    automatic_success: list[SpellRequirementSchema] = Field(default_factory=list)
    automatic_failure: list[SpellRequirementSchema] = Field(default_factory=list)
    save_modifiers: list[SpellSaveModifierSchema] = Field(default_factory=list)
    failure: OutcomeSchema
    success: OutcomeSchema = Field(default_factory=OutcomeSchema)
    success_damage: Literal["none", "half"] = "none"
    repeat_save: RepeatSaveProgressionSchema | None = None


class SpellAttackResolutionSchema(SpellMechanicsSchemaModel):
    type: Literal["spell_attack"]
    mode: Literal["melee", "ranged"]
    attacks: PositiveInt = 1
    allocation: Literal["same_target", "same_or_different"] = "same_target"
    hit: OutcomeSchema
    miss: OutcomeSchema = Field(default_factory=OutcomeSchema)


class AbilityCheckResolutionSchema(SpellMechanicsSchemaModel):
    type: Literal["ability_check"]
    ability: Ability | Literal["spellcasting"]
    dc: PositiveInt | Literal["spell_save_dc", "ten_plus_spell_level"]
    success: OutcomeSchema
    failure: OutcomeSchema = Field(default_factory=OutcomeSchema)


class ContestedCheckResolutionSchema(SpellMechanicsSchemaModel):
    type: Literal["contested_check"]
    source_ability: Ability | Literal["spellcasting"]
    target_abilities: list[Ability] = Field(min_length=1)
    target_chooses_ability: bool = False
    tie: Literal["source", "target", "no_change"] = "no_change"
    source_wins: OutcomeSchema
    target_wins: OutcomeSchema = Field(default_factory=OutcomeSchema)


class HitPointPoolResolutionSchema(SpellMechanicsSchemaModel):
    type: Literal["hit_point_pool"]
    dice: str = Field(pattern=r"^\d+d\d+$")
    bonus: int = 0
    order: Literal[
        "ascending_current_hit_points", "closest_first", "source_choice"
    ] = "ascending_current_hit_points"
    cost: Literal["current_hit_points", "maximum_hit_points"] = "current_hit_points"
    on_covered: OutcomeSchema
    stop_when_next_target_exceeds_pool: bool = False


class RepeatResolutionSchema(SpellMechanicsSchemaModel):
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
    def validate_propagation(self) -> "RepeatResolutionSchema":
        if self.allocation == "propagating" and self.propagation_range_feet is None:
            raise ValueError("Propagating resolution requires a propagation range.")
        return self


class SequenceStepSchema(SpellMechanicsSchemaModel):
    resolution: SpellResolutionSchema
    target: SpellTargetSchema | None = None


class SequenceResolutionSchema(SpellMechanicsSchemaModel):
    type: Literal["sequence"]
    steps: list[SequenceStepSchema] = Field(min_length=1)


class ResolutionChoiceOptionSchema(SpellMechanicsSchemaModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    resolution: SpellResolutionSchema
    implementation: SpellImplementationSchema | None = None


class ChoiceResolutionSchema(SpellMechanicsSchemaModel):
    type: Literal["choice"]
    count: PositiveInt = 1
    options: list[ResolutionChoiceOptionSchema] = Field(min_length=1)


class RandomResolutionEntrySchema(SpellMechanicsSchemaModel):
    minimum: PositiveInt
    maximum: PositiveInt
    resolution: SpellResolutionSchema

    @model_validator(mode="after")
    def validate_range(self) -> "RandomResolutionEntrySchema":
        if self.minimum > self.maximum:
            raise ValueError("Random result minimum cannot exceed maximum.")
        return self


class RandomTableResolutionSchema(SpellMechanicsSchemaModel):
    type: Literal["random_table"]
    die: str = Field(pattern=r"^\d+d\d+$")
    per_target: bool = False
    entries: list[RandomResolutionEntrySchema] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_entries(self) -> "RandomTableResolutionSchema":
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
    pass


class RepeatSaveProgressionSchema(SpellMechanicsSchemaModel):
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


class GrantedActionSchema(SpellMechanicsSchemaModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    economy: Literal["action", "bonus_action", "reaction", "magic_action"]
    target: SpellTargetSchema
    resolution: SpellResolutionSchema
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)
    target_history: Literal[
        "none", "exclude_successful_save", "exclude_any_previous_target"
    ] = "none"


class AreaTriggerSchema(SpellMechanicsSchemaModel):
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


class AreaMovementSchema(SpellMechanicsSchemaModel):
    trigger: Literal["source_turn_start", "source_turn_end", "granted_action"]
    distance_feet: PositiveInt
    direction: Literal["away_from_source", "chosen", "fixed"]
    movement_mode: Literal["ground", "flying", "unrestricted"] = "unrestricted"


class RandomTableEntrySchema(SpellMechanicsSchemaModel):
    minimum: PositiveInt
    maximum: PositiveInt
    resolution: SpellResolutionSchema

    @model_validator(mode="after")
    def validate_range(self) -> "RandomTableEntrySchema":
        if self.minimum > self.maximum:
            raise ValueError("Random result minimum cannot exceed maximum.")
        return self


class RandomTableSchema(SpellMechanicsSchemaModel):
    die: str = Field(pattern=r"^\d+d\d+$")
    entries: list[RandomTableEntrySchema] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_entries(self) -> "RandomTableSchema":
        _validate_complete_roll_table(self.die, self.entries)
        return self


class CastingTriggerSchema(SpellMechanicsSchemaModel):
    event: Literal[
        "attack_hit",
        "creature_damaged",
        "spell_cast",
        "targeted_by_attack",
        "falling",
    ]
    timing: Literal["before_resolution", "immediately_after", "after_resolution"]
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)
    target: EventSpellTargetSchema | None = None


class SlotScalingIncrementSchema(SpellMechanicsSchemaModel):
    type: Literal[
        "damage_dice",
        "healing_dice",
        "healing_bonus",
        "temporary_hit_points",
        "target_count",
        "projectile_count",
        "area_radius_feet",
        "duration",
    ]
    amount: PositiveInt | str
    damage_type: str | None = None


class SlotScalingSchema(SpellMechanicsSchemaModel):
    type: Literal["slot_level"] = "slot_level"
    above_level: NonNegativeInt | Literal["spell_level"] = "spell_level"
    per_level: list[SlotScalingIncrementSchema] = Field(min_length=1)


class CasterLevelScalingThresholdSchema(SpellMechanicsSchemaModel):
    minimum_level: PositiveInt
    projectile_count: PositiveInt


class CasterLevelScalingSchema(SpellMechanicsSchemaModel):
    type: Literal["caster_level"]
    thresholds: list[CasterLevelScalingThresholdSchema] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "CasterLevelScalingSchema":
        levels = [threshold.minimum_level for threshold in self.thresholds]
        if levels != sorted(set(levels)):
            raise ValueError("Caster-level thresholds must be unique and sorted.")
        if levels[0] != 1:
            raise ValueError("Caster-level scaling must define a level 1 baseline.")
        return self


class OutcomeTriggerSchema(SpellMechanicsSchemaModel):
    event: Literal[
        "targeted_by_attack",
        "attack_would_hit",
        "attack_hit",
        "targeted_by_spell",
        "spell_cast_nearby",
        "before_target_damaged",
        "target_damaged",
        "target_makes_attack",
        "target_casts_spell",
        "target_deals_damage",
        "adjacent_creature_wakes_target",
        "source_damaged",
        "before_target_reduced_to_zero",
        "target_reduced_to_zero",
        "target_killed",
        "source_turn_start",
        "source_turn_end",
        "target_turn_start",
        "target_turn_end",
        "source_moves",
        "target_moves",
        "effect_ended",
    ]
    attribution: Literal["this_effect", "this_spell", "source"] = "this_spell"
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)
    delay_trigger: Literal[
        "none", "source_turn_start", "source_turn_end", "target_turn_start"
    ] = "none"
    turn_offset: NonNegativeInt = 0
    target: EventSpellTargetSchema | None = None
    per_target_limit: PositiveInt | None = None
    limit_period: Literal["turn", "round", "spell_instance"] | None = None
    resolution: SpellResolutionSchema


class SpellMechanicsSchema(SpellMechanicsSchemaModel):
    target: SpellTargetSchema
    resolution: SpellResolutionSchema
    casting_requirements: list[SpellRequirementSchema] = Field(default_factory=list)
    casting_trigger: CastingTriggerSchema | None = None
    scaling: list[
        Annotated[
            SlotScalingSchema | CasterLevelScalingSchema,
            Field(discriminator="type"),
        ]
    ] = Field(default_factory=list)
    outcome_triggers: list[OutcomeTriggerSchema] = Field(default_factory=list)
    condition_application: Literal["all", "choose_one"] = "all"
    self_removal_blocked_conditions: list[str] = Field(default_factory=list)


AnyRequirementSchema.model_rebuild()
AllRequirementSchema.model_rebuild()
TargetChoiceOptionSchema.model_rebuild()
ChoiceSpellTargetSchema.model_rebuild()
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
