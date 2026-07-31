from __future__ import annotations

from typing import TYPE_CHECKING

from ..effects.condition_rules import (
    EffectiveConditionSet,
    effective_conditions,
)
from ..effects.conditions import CombatTrait
from .actions.eligibility import (
    ActionEligibility,
    EligibilityFailure,
    action_eligibility,
)

if TYPE_CHECKING:
    from .encounter import EncounterState
    from .models import CreatureRef, EncounterAction


class CombatRules:
    def effective_conditions(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
    ) -> EffectiveConditionSet:
        return effective_conditions(state.conditions_for(creature_ref))

    def action_eligibility(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> ActionEligibility:
        return action_eligibility(state, actor_ref, action)

    def reaction_eligibility(
        self,
        state: EncounterState,
        reactor_ref: CreatureRef,
    ) -> ActionEligibility:
        reactor = state.creatures[reactor_ref]
        failures: list[EligibilityFailure] = []
        if not reactor.is_alive:
            failures.append(
                EligibilityFailure(
                    "reactor_defeated",
                    "A defeated creature cannot take reactions.",
                )
            )
        if not reactor.reaction_available:
            failures.append(
                EligibilityFailure(
                    "reaction_spent",
                    "No Reaction remains.",
                )
            )
        effective = self.effective_conditions(state, reactor_ref)
        if effective.has_trait(CombatTrait.CANNOT_TAKE_REACTIONS):
            failures.append(
                EligibilityFailure(
                    "condition.cannot_take_reactions",
                    "This creature cannot take reactions.",
                    effective.providers_for_trait(
                        CombatTrait.CANNOT_TAKE_REACTIONS
                    ),
                )
            )
        return ActionEligibility(tuple(failures))


COMBAT_RULES = CombatRules()
