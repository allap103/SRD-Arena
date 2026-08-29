"""Stable entry point for encounter action eligibility rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..encounter_models.actions import (
    CreatureRef,
    EncounterAction,
)
from ..rule_queries.permissions import action_compatibility
from .eligibility_rules.attacks import AttackRule, GrappleRule
from .eligibility_rules.capabilities import FeatureActionRule, StatBlockActionRule
from .eligibility_rules.common import (
    ActorOwnershipRule,
    ActorReadyRule,
    MovementRule,
    ResourceRule,
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
    """Collect every reason a candidate action is currently unavailable."""

    compatibility = action_compatibility(
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
]
