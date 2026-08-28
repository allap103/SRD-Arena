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
from .errors import CapabilityBuildError
from .requirements import (
    ActionRequirementSchema,
    ConditionRequirementSchema,
    CreatureTypeRequirementSchema,
    NotAffectedRequirementSchema,
    SizeRequirementSchema,
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
from .targets import (
    ActionTargetSchema,
    AreaTargetSchema,
    CreatureTargetSchema,
    SelfTargetSchema,
)

__all__ = [
    "Ability",
    "ActionEffectSchema",
    "ActionRequirementSchema",
    "ActionTargetSchema",
    "AreaTargetSchema",
    "AutomaticResolutionSchema",
    "CapabilityBuildError",
    "CapabilitySchemaModel",
    "ConditionEffectSchema",
    "ConditionRequirementSchema",
    "ControlEffectSchema",
    "CreatureTargetSchema",
    "CreatureTypeRequirementSchema",
    "DamageEffectSchema",
    "DerivedDifficultyClassSchema",
    "DifficultyClassSchema",
    "EffectDurationSchema",
    "FixedDifficultyClassSchema",
    "ForcedMovementEffectSchema",
    "GainMemoriesEffectSchema",
    "NonNegativeInt",
    "NotAffectedRequirementSchema",
    "OutcomeSchema",
    "PositiveInt",
    "ProhibitReactionEffectSchema",
    "ResolutionSchemaModel",
    "RollModifierEffectSchema",
    "SavingThrowResolutionSchema",
    "SelfTargetSchema",
    "SizeRequirementSchema",
    "SpeedMultiplierEffectSchema",
    "TimedDurationSchema",
    "TurnEconomyRestrictionEffectSchema",
]
