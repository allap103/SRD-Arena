from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from pydantic import Field, RootModel, model_validator

from srd_arena.content.common.implementation import ImplementationSchema

from .targets import (
    AreaGeometrySchema,
    CapabilityTargetSchema,
    EventTargetSchema,
)
from srd_arena.content.capabilities.schemas.base import (
    Ability,
    CapabilitySchemaModel,
    NonNegativeInt,
    PositiveInt,
)
from srd_arena.content.capabilities.schemas.durations import EffectDurationSchema
from srd_arena.content.capabilities.schemas.effects import (
    AccumulateDiceEffectSchema,
    AccumulatedDamageEffectSchema,
    ActionFailureChanceEffectSchema,
    ArmorClassModifierEffectSchema,
    AttackLimitEffectSchema,
    BattlefieldRemovalEffectSchema,
    CancelPendingEventEffectSchema,
    CompelledBehaviorEffectSchema,
    ConditionEffectSchema,
    ConditionImmunityEffectSchema,
    ConditionSaveAdvantageEffectSchema,
    DamageEffectSchema,
    DamageImmunityEffectSchema,
    DamageReductionEffectSchema,
    DamageResistanceEffectSchema,
    DifficultTerrainEffectSchema,
    CreatedEntityStatisticsSchema,
    ExtraActionEffectSchema,
    ExtraTurnsEffectSchema,
    ForcedMovementEffectSchema,
    HealingEffectSchema,
    HitPointMaximumModifierEffectSchema,
    LightEffectSchema,
    MirroredDamageEffectSchema,
    MovementModeEffectSchema,
    ObscurementEffectSchema,
    PreventDefeatEffectSchema,
    ProhibitReactionEffectSchema,
    RemoveEffectSchema,
    RelationshipEffectSchema,
    ReplaceWithCreatureEffectSchema,
    RequireTargetReselectionEffectSchema,
    RedirectPendingTargetEffectSchema,
    RollModifierEffectSchema,
    SenseEffectSchema,
    SpeedModifierEffectSchema,
    SpeedMultiplierEffectSchema,
    SummonEffectSchema,
    SuppressMagicEffectSchema,
    TeleportEffectSchema,
    TemporaryHitPointsEffectSchema,
    TurnEconomyRestrictionEffectSchema,
    TransformEffectSchema,
    TransformObjectEffectSchema,
)
from srd_arena.content.capabilities.schemas.requirements import (
    CapabilityRequirementSchema,
)
from srd_arena.content.capabilities.schemas.resolutions import (
    AttackResolutionSchema as SharedAttackResolutionSchema,
    AutomaticResolutionSchema as SharedAutomaticResolutionSchema,
    DerivedDifficultyClassSchema,
    OutcomeSchema as SharedOutcomeSchema,
    RepeatResolutionSchemaBase,
    RepeatSaveProgressionSchemaBase,
    SavingThrowResolutionSchema as SharedSavingThrowResolutionSchema,
    SequenceResolutionSchemaBase,
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


class CreateEntityEffectSchema(CapabilitySchemaModel):
    type: Literal["create_entity"]
    entity_id: str = Field(min_length=1)
    entity_kind: Literal["manifestation", "weapon", "hand", "hazard", "image"]
    targetable: bool = False
    occupies_space: bool = False
    geometry: AreaGeometrySchema | None = None
    statistics: CreatedEntityStatisticsSchema | None = None
    movement: AreaMovementSchema | None = None
    actions: list[GrantedActionSchema] = Field(default_factory=list)


class StoreCapabilityEffectSchema(CapabilitySchemaModel):
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
    activation_target: EventTargetSchema | None = None
    inherit_casting_statistics: bool = True
    spell_name: str | None = None
    spell_source: str | None = None
    stored_resolution: CapabilityResolutionSchema | None = None

    @model_validator(mode="after")
    def validate_stored_payload(self) -> "StoreCapabilityEffectSchema":
        if (self.spell_name is None) == (self.stored_resolution is None):
            raise ValueError(
                "Stored spell effects require exactly one spell or authored resolution."
            )
        return self


class GrantActionEffectSchema(CapabilitySchemaModel):
    type: Literal["grant_action"]
    action: GrantedActionSchema


class CreatePersistentAreaEffectSchema(CapabilitySchemaModel):
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
            "parent_capability_ends",
        ]
    ] = Field(default_factory=list)


class RandomOutcomeEffectSchema(CapabilitySchemaModel):
    type: Literal["random_outcome"]
    table: RandomTableSchema


class OngoingModifierGroupEffectSchema(CapabilitySchemaModel):
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


class CapabilityEffectSchema(
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
            | CreateEntityEffectSchema
            | TransformObjectEffectSchema
            | AccumulateDiceEffectSchema
            | AccumulatedDamageEffectSchema
            | StoreCapabilityEffectSchema
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


class OutcomeSchema(SharedOutcomeSchema[CapabilityEffectSchema]):
    pass


class AutomaticResolutionSchema(SharedAutomaticResolutionSchema[OutcomeSchema]):
    pass


class SavingThrowResolutionSchema(
    SharedSavingThrowResolutionSchema[OutcomeSchema, OutcomeSchema]
):
    ability: Ability | None = None
    difficulty: DerivedDifficultyClassSchema = Field(
        default_factory=lambda: DerivedDifficultyClassSchema(type="spell_save_dc")
    )
    use_provider_metadata_ability: bool = True
    success: OutcomeSchema = Field(default_factory=OutcomeSchema)
    repeat_save: RepeatSaveProgressionSchema | None = None


class DerivedAttackResolutionSchema(SharedAttackResolutionSchema[OutcomeSchema]):
    miss: OutcomeSchema = Field(default_factory=OutcomeSchema)


class AbilityCheckResolutionSchema(CapabilitySchemaModel):
    type: Literal["ability_check"]
    ability: Ability | Literal["spellcasting"]
    dc: PositiveInt | Literal["spell_save_dc", "ten_plus_spell_level"]
    success: OutcomeSchema
    failure: OutcomeSchema = Field(default_factory=OutcomeSchema)


class ContestedCheckResolutionSchema(CapabilitySchemaModel):
    type: Literal["contested_check"]
    source_ability: Ability | Literal["spellcasting"]
    target_abilities: list[Ability] = Field(min_length=1)
    target_chooses_ability: bool = False
    tie: Literal["source", "target", "no_change"] = "no_change"
    source_wins: OutcomeSchema
    target_wins: OutcomeSchema = Field(default_factory=OutcomeSchema)


class HitPointPoolResolutionSchema(CapabilitySchemaModel):
    type: Literal["hit_point_pool"]
    dice: str = Field(pattern=r"^\d+d\d+$")
    bonus: int = 0
    order: Literal["ascending_current_hit_points", "closest_first", "source_choice"] = (
        "ascending_current_hit_points"
    )
    cost: Literal["current_hit_points", "maximum_hit_points"] = "current_hit_points"
    on_covered: OutcomeSchema
    stop_when_next_target_exceeds_pool: bool = False


class RepeatResolutionSchema(RepeatResolutionSchemaBase):
    resolution: CapabilityResolutionSchema


class SequenceStepSchema(CapabilitySchemaModel):
    resolution: CapabilityResolutionSchema
    target: CapabilityTargetSchema | None = None


class SequenceResolutionSchema(SequenceResolutionSchemaBase):
    steps: list[SequenceStepSchema] = Field(min_length=1)


class ResolutionChoiceOptionSchema(CapabilitySchemaModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    resolution: CapabilityResolutionSchema
    implementation: ImplementationSchema | None = None


class ChoiceResolutionSchema(CapabilitySchemaModel):
    type: Literal["choice"]
    count: PositiveInt = 1
    options: list[ResolutionChoiceOptionSchema] = Field(min_length=1)


class RandomResolutionEntrySchema(CapabilitySchemaModel):
    minimum: PositiveInt
    maximum: PositiveInt
    resolution: CapabilityResolutionSchema

    @model_validator(mode="after")
    def validate_range(self) -> "RandomResolutionEntrySchema":
        if self.minimum > self.maximum:
            raise ValueError("Random result minimum cannot exceed maximum.")
        return self


class RandomTableResolutionSchema(CapabilitySchemaModel):
    type: Literal["random_table"]
    die: str = Field(pattern=r"^\d+d\d+$")
    per_target: bool = False
    entries: list[RandomResolutionEntrySchema] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_entries(self) -> "RandomTableResolutionSchema":
        _validate_complete_roll_table(self.die, self.entries)
        return self


class CapabilityResolutionSchema(
    RootModel[
        Annotated[
            AutomaticResolutionSchema
            | SavingThrowResolutionSchema
            | DerivedAttackResolutionSchema
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


class RepeatSaveProgressionSchema(RepeatSaveProgressionSchemaBase):
    on_success: CapabilityResolutionSchema = Field(
        default_factory=lambda: CapabilityResolutionSchema.model_validate(
            {"type": "automatic", "outcome": {"end_capability": True}}
        )
    )
    on_failure: CapabilityResolutionSchema | None = None


class GrantedActionSchema(CapabilitySchemaModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    economy: Literal["action", "bonus_action", "reaction", "magic_action"]
    target: CapabilityTargetSchema
    resolution: CapabilityResolutionSchema
    requirements: list[CapabilityRequirementSchema] = Field(default_factory=list)
    target_history: Literal[
        "none", "exclude_successful_save", "exclude_any_previous_target"
    ] = "none"


class AreaTriggerSchema(CapabilitySchemaModel):
    event: Literal[
        "created",
        "creature_enters",
        "area_enters_creature_space",
        "creature_turn_start",
        "creature_turn_end",
    ]
    resolution: CapabilityResolutionSchema
    per_target_limit: PositiveInt | None = None
    limit_period: Literal["turn", "round", "capability_instance"] | None = None


class AreaMovementSchema(CapabilitySchemaModel):
    trigger: Literal["source_turn_start", "source_turn_end", "granted_action"]
    distance_feet: PositiveInt
    direction: Literal["away_from_source", "chosen", "fixed"]
    movement_mode: Literal["ground", "flying", "unrestricted"] = "unrestricted"


class RandomTableEntrySchema(CapabilitySchemaModel):
    minimum: PositiveInt
    maximum: PositiveInt
    resolution: CapabilityResolutionSchema

    @model_validator(mode="after")
    def validate_range(self) -> "RandomTableEntrySchema":
        if self.minimum > self.maximum:
            raise ValueError("Random result minimum cannot exceed maximum.")
        return self


class RandomTableSchema(CapabilitySchemaModel):
    die: str = Field(pattern=r"^\d+d\d+$")
    entries: list[RandomTableEntrySchema] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_entries(self) -> "RandomTableSchema":
        _validate_complete_roll_table(self.die, self.entries)
        return self


GrantActionEffectSchema.model_rebuild()
CreatePersistentAreaEffectSchema.model_rebuild()
CreateEntityEffectSchema.model_rebuild()
StoreCapabilityEffectSchema.model_rebuild()
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
