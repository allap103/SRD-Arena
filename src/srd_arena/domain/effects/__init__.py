"""Expose the public effects package API."""

from .application import apply_effects, message_effects, serialize_effects
from .condition_rules import (
    EffectiveCondition,
    EffectiveConditionSet,
    EffectiveTrait,
    SuppressedCondition,
)
from .conditions import (
    AppliedCondition,
    CombatTrait,
    Condition,
    build_applied_condition,
)
from .results import EffectResult
from .rule_effects import (
    ActionEconomyKind,
    ActionEconomyRestriction,
    ArmorClassAdjustment,
    AttackLimit,
    InvocationFailureChance,
    ReactionProhibition,
    RollAdjustment,
    RuntimeRuleEffect,
    SpeedAdjustment,
    SpeedMultiplier,
)
from .runtime import (
    CreatureRelationship,
    EffectPolarity,
    EffectSource,
    EffectSourceKind,
    OngoingEffect,
    RelationshipKind,
    RuntimeStateIdentity,
)
from .triggered import TriggeredEffect, matching_effects, reroll_eligible_indices

__all__ = [
    "ActionEconomyKind",
    "ActionEconomyRestriction",
    "AppliedCondition",
    "ArmorClassAdjustment",
    "AttackLimit",
    "CombatTrait",
    "Condition",
    "CreatureRelationship",
    "EffectPolarity",
    "EffectResult",
    "EffectSource",
    "EffectSourceKind",
    "EffectiveCondition",
    "EffectiveConditionSet",
    "EffectiveTrait",
    "InvocationFailureChance",
    "OngoingEffect",
    "ReactionProhibition",
    "RelationshipKind",
    "RollAdjustment",
    "RuntimeRuleEffect",
    "RuntimeStateIdentity",
    "SpeedAdjustment",
    "SpeedMultiplier",
    "SuppressedCondition",
    "TriggeredEffect",
    "apply_effects",
    "build_applied_condition",
    "matching_effects",
    "message_effects",
    "reroll_eligible_indices",
    "serialize_effects",
]
