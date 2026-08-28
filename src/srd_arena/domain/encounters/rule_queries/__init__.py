"""Typed, source-aware questions asked by encounter orchestration."""

from .defenses import (
    apply_damage,
    condition_immunities,
    condition_suppressions,
    damage_resistances,
    has_condition_save_advantage,
    reset_damage_reductions,
    resolve_damage_reduction,
)
from .health import apply_healing, effective_maximum_health
from .invocations import invocation_start_checks, resolve_invocation_start
from .models import (
    InvocationFailureChanceContribution,
    InvocationStartContext,
    InvocationStartQueryResult,
    InvocationStartResult,
    InvocationStartRoll,
    MovementQueryResult,
    NumericOperation,
    NumericRuleContribution,
    NumericRuleResult,
    RollRuleContribution,
    RollRuleResult,
    SenseRuleResult,
    SetRuleResult,
    SourcedEligibilityFailure,
    SourcedRuleContribution,
)
from .numeric import (
    attack_limit,
    effective_armor_class,
    effective_speed,
    movement_budget,
)
from .permissions import action_compatibility, reaction_eligibility
from .rolls import roll_modifiers
from .senses import sense_range

__all__ = [
    "InvocationFailureChanceContribution",
    "InvocationStartContext",
    "InvocationStartQueryResult",
    "InvocationStartResult",
    "InvocationStartRoll",
    "MovementQueryResult",
    "NumericOperation",
    "NumericRuleContribution",
    "NumericRuleResult",
    "RollRuleContribution",
    "RollRuleResult",
    "SenseRuleResult",
    "SetRuleResult",
    "SourcedEligibilityFailure",
    "SourcedRuleContribution",
    "action_compatibility",
    "apply_damage",
    "apply_healing",
    "attack_limit",
    "condition_immunities",
    "condition_suppressions",
    "damage_resistances",
    "effective_armor_class",
    "effective_maximum_health",
    "effective_speed",
    "has_condition_save_advantage",
    "invocation_start_checks",
    "movement_budget",
    "reaction_eligibility",
    "reset_damage_reductions",
    "resolve_damage_reduction",
    "resolve_invocation_start",
    "roll_modifiers",
    "sense_range",
]
