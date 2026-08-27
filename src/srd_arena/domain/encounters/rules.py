from __future__ import annotations

from typing import TYPE_CHECKING

from ..effects.condition_rules import (
    EffectiveConditionSet,
    effective_conditions,
)
from ..effects.modifiers import ModifierSubject, RollKind
from ..rolls.dice import DieRoller
from .actions.eligibility import (
    ActionEligibility,
    action_eligibility,
)
from .rule_queries import (
    InvocationStartContext,
    InvocationStartQueryResult,
    InvocationStartResult,
    MovementQueryResult,
    NumericRuleResult,
    RollRuleResult,
    action_compatibility,
    attack_limit,
    effective_armor_class,
    effective_speed,
    invocation_start_checks,
    movement_budget,
    reaction_eligibility,
    resolve_invocation_start,
    roll_modifiers,
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
        return effective_conditions(
            state.conditions_for(creature_ref),
            state.creatures[creature_ref].creature.statistics.condition_immunities,
        )

    def action_eligibility(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> ActionEligibility:
        return action_eligibility(state, actor_ref, action)

    def action_compatibility(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> ActionEligibility:
        return action_compatibility(state, actor_ref, action)

    def reaction_eligibility(
        self,
        state: EncounterState,
        reactor_ref: CreatureRef,
        reaction_kind: str | None = None,
    ) -> ActionEligibility:
        return reaction_eligibility(state, reactor_ref, reaction_kind)

    def effective_armor_class(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
    ) -> NumericRuleResult:
        return effective_armor_class(state, creature_ref)

    def effective_speed(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
    ) -> NumericRuleResult:
        return effective_speed(state, creature_ref)

    def movement_budget(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
    ) -> MovementQueryResult:
        return movement_budget(state, creature_ref)

    def attack_limit(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        base: int,
    ) -> NumericRuleResult:
        return attack_limit(state, creature_ref, base)

    def roll_modifiers(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        roll: RollKind,
        ability: str | None = None,
        subject: ModifierSubject = "target",
        opposing_ref: CreatureRef | None = None,
    ) -> RollRuleResult:
        return roll_modifiers(
            state,
            creature_ref,
            roll,
            ability,
            subject,
            opposing_ref,
        )

    def invocation_start_checks(
        self,
        state: EncounterState,
        context: InvocationStartContext,
    ) -> InvocationStartQueryResult:
        return invocation_start_checks(state, context)

    def resolve_invocation_start(
        self,
        query: InvocationStartQueryResult,
        roller: DieRoller,
    ) -> InvocationStartResult:
        return resolve_invocation_start(query, roller)


COMBAT_RULES = CombatRules()
