"""Typed, source-aware questions asked by encounter orchestration."""

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
    SourcedEligibilityFailure,
)
from .numeric import (
    attack_limit,
    effective_armor_class,
    effective_speed,
    movement_budget,
)
from .permissions import action_compatibility, reaction_eligibility
from .rolls import roll_modifiers

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
    "SourcedEligibilityFailure",
    "action_compatibility",
    "attack_limit",
    "effective_armor_class",
    "effective_speed",
    "invocation_start_checks",
    "movement_budget",
    "reaction_eligibility",
    "resolve_invocation_start",
    "roll_modifiers",
]
