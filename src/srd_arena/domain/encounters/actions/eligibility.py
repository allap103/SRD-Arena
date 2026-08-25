"""Stable entry point for encounter action eligibility rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import CreatureRef, EncounterAction
from .eligibility_rules.attacks import AttackRule, GrappleRule
from .eligibility_rules.capabilities import FeatureActionRule, StatBlockActionRule
from .eligibility_rules.common import (
    ActorOwnershipRule,
    ActorReadyRule,
    MovementRule,
    ResourceRule,
    opposing_target_failure,
    target_requirement_failure,
)
from .eligibility_rules.models import (
    ActionEligibility,
    EligibilityFailure,
    EligibilityRule,
)
from .eligibility_rules.spells import SpellActionRule, SpellTargetSelectionRule

if TYPE_CHECKING:
    from ..encounter import EncounterState


ACTION_ELIGIBILITY_RULES: tuple[EligibilityRule, ...] = (
    ResourceRule(),
    MovementRule(),
    AttackRule(),
    GrappleRule(),
    StatBlockActionRule(),
    FeatureActionRule(),
    SpellTargetSelectionRule(),
    SpellActionRule(),
)


def action_eligibility(
    state: EncounterState,
    actor_ref: CreatureRef,
    action: EncounterAction,
) -> ActionEligibility:
    compatibility = state.combat_rules.action_compatibility(
        state,
        actor_ref,
        action,
    )
    failures = compatibility.failures + tuple(
        failure
        for rule in ACTION_ELIGIBILITY_RULES
        if (failure := rule.check(state, actor_ref, action)) is not None
    )
    return ActionEligibility(failures)


def require_action_eligible(
    state: EncounterState,
    actor_ref: CreatureRef,
    action: EncounterAction,
) -> None:
    eligibility = state.combat_rules.action_eligibility(
        state,
        actor_ref,
        action,
    )
    if eligibility.allowed:
        return
    raise ValueError(eligibility.failures[0].message)


# Preserve the former module-local names for internal callers and diagnostics.
_opposing_target_failure = opposing_target_failure
_target_requirement_failure = target_requirement_failure


__all__ = [
    "ACTION_ELIGIBILITY_RULES",
    "ActionEligibility",
    "ActorOwnershipRule",
    "ActorReadyRule",
    "AttackRule",
    "EligibilityFailure",
    "EligibilityRule",
    "FeatureActionRule",
    "GrappleRule",
    "MovementRule",
    "ResourceRule",
    "SpellActionRule",
    "SpellTargetSelectionRule",
    "StatBlockActionRule",
    "action_eligibility",
    "require_action_eligible",
]
