"""Schema vocabulary shared by independently authored content concepts."""

from .base import Ability, CapabilitySchemaModel, NonNegativeInt, PositiveInt
from .durations import EffectDurationSchema, TimedDurationSchema
from .effects import (
    ActionEffectSchema,
    ConditionEffectSchema,
    ControlEffectSchema,
    DamageEffectSchema,
    ForcedMovementEffectSchema,
    GainMemoriesEffectSchema,
    ProhibitReactionEffectSchema,
    RollModifierEffectSchema,
    SpeedMultiplierEffectSchema,
    TurnEconomyRestrictionEffectSchema,
)
from .requirements import (
    ActionRequirementSchema,
    ConditionRequirementSchema,
    CreatureTypeRequirementSchema,
    NotAffectedRequirementSchema,
    SizeRequirementSchema,
)
from .targets import (
    ActionTargetSchema,
    AreaTargetSchema,
    CreatureTargetSchema,
    SelfTargetSchema,
)
from .resolutions import (
    AutomaticResolutionSchema,
    DerivedDifficultyClassSchema,
    DifficultyClassSchema,
    FixedDifficultyClassSchema,
    OutcomeSchema,
    ResolutionSchemaModel,
    SavingThrowResolutionSchema,
)

__all__ = [
    "Ability",
    "AutomaticResolutionSchema",
    "ActionEffectSchema",
    "CapabilitySchemaModel",
    "ActionRequirementSchema",
    "ActionTargetSchema",
    "AreaTargetSchema",
    "ConditionEffectSchema",
    "ConditionRequirementSchema",
    "ControlEffectSchema",
    "CreatureTargetSchema",
    "CreatureTypeRequirementSchema",
    "DamageEffectSchema",
    "DerivedDifficultyClassSchema",
    "DifficultyClassSchema",
    "EffectDurationSchema",
    "ForcedMovementEffectSchema",
    "FixedDifficultyClassSchema",
    "GainMemoriesEffectSchema",
    "NonNegativeInt",
    "NotAffectedRequirementSchema",
    "OutcomeSchema",
    "PositiveInt",
    "ProhibitReactionEffectSchema",
    "RollModifierEffectSchema",
    "ResolutionSchemaModel",
    "SavingThrowResolutionSchema",
    "SelfTargetSchema",
    "SizeRequirementSchema",
    "SpeedMultiplierEffectSchema",
    "TimedDurationSchema",
    "TurnEconomyRestrictionEffectSchema",
]
