"""The authored capability schemas currently supported by the runtime builder."""

from srd_arena.content.capabilities.schemas import (
    effects,
    requirements,
    resolutions,
    targets,
)

EXECUTABLE_TARGET_TYPES = (
    targets.SelfTargetSchema,
    targets.CreatureTargetSchema,
    targets.AreaTargetSchema,
    targets.ActionCreatureTargetSchema,
    targets.ActionAreaTargetSchema,
)

EXECUTABLE_RESOLUTION_TYPES = (
    resolutions.AutomaticResolutionSchema,
    resolutions.SavingThrowResolutionSchema,
    resolutions.AttackResolutionSchema,
    resolutions.FixedAttackResolutionSchema,
    resolutions.RepeatResolutionSchemaBase,
    resolutions.SequenceResolutionSchemaBase,
)

EXECUTABLE_EFFECT_TYPES = (
    effects.DamageEffectSchema,
    effects.HealingEffectSchema,
    effects.TemporaryHitPointsEffectSchema,
    effects.ArmorClassModifierEffectSchema,
    effects.RemoveEffectSchema,
    effects.DamageResistanceEffectSchema,
    effects.DamageReductionEffectSchema,
    effects.SpeedModifierEffectSchema,
    effects.ConditionSaveAdvantageEffectSchema,
    effects.DamageImmunityEffectSchema,
    effects.ConditionImmunityEffectSchema,
    effects.SenseEffectSchema,
    effects.HitPointMaximumModifierEffectSchema,
    effects.ConditionEffectSchema,
    effects.ForcedMovementEffectSchema,
    effects.SpeedMultiplierEffectSchema,
    effects.ProhibitReactionEffectSchema,
    effects.TurnEconomyRestrictionEffectSchema,
    effects.RollModifierEffectSchema,
    effects.ControlEffectSchema,
    effects.GainMemoriesEffectSchema,
)

EXECUTABLE_REQUIREMENT_TYPES = (
    requirements.AllRequirementSchema,
    requirements.AnyRequirementSchema,
    requirements.ConditionRequirementSchema,
    requirements.ConditionImmunityRequirementSchema,
    requirements.CreatureTraitRequirementSchema,
    requirements.CreatureTypeRequirementSchema,
    requirements.FreeHandRequirementSchema,
    requirements.HitPointRequirementSchema,
    requirements.NotAffectedRequirementSchema,
    requirements.PerceptionRequirementSchema,
    requirements.RelationshipRequirementSchema,
    requirements.SizeRequirementSchema,
)
