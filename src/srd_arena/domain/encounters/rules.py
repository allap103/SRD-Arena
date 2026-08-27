"""Expose source-aware combat rule queries through one stable service facade."""

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
    """Answer combat questions by composing creature, condition, and effect state.

    The service is stateless: encounter data remains on ``EncounterState`` and
    each query returns a value carrying the contributions behind its answer.
    """

    def effective_conditions(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
    ) -> EffectiveConditionSet:
        """Resolve active conditions after immunity and implication rules.

        >>> from unittest.mock import Mock
        >>> creature = Mock()
        >>> creature.statistics.condition_immunities = frozenset()
        >>> state = Mock(creatures={"hero": Mock(creature=creature)})
        >>> state.conditions_for.return_value = ()
        >>> CombatRules().effective_conditions(state, "hero").conditions
        ()
        """
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
        """Return every rule failure that prevents selecting an action.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.encounters.models import EncounterAction
        >>> actor = Mock(is_alive=True, movement_remaining=0, actions_remaining=1,
        ...     bonus_action_available=True, bonus_action_used_this_turn=False,
        ...     action_used_this_turn=False)
        >>> actor.creature.condition_immunities.return_value = frozenset()
        >>> state = Mock(creatures={"hero": actor}, conditions=[], ongoing_effects=[])
        >>> state.combat_rules = CombatRules()
        >>> action = EncounterAction("Wait", "wait", creature_ref="hero")
        >>> state.combat_rules.action_eligibility(state, "hero", action).allowed
        True
        """
        return action_eligibility(state, actor_ref, action)

    def action_compatibility(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> ActionEligibility:
        """Check actor identity, survival, permissions, and action economy.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.encounters.models import EncounterAction
        >>> actor = Mock(is_alive=True, actions_remaining=1,
        ...     bonus_action_available=True, bonus_action_used_this_turn=False,
        ...     action_used_this_turn=False)
        >>> actor.creature.condition_immunities.return_value = frozenset()
        >>> state = Mock(creatures={"hero": actor}, conditions=[], ongoing_effects=[])
        >>> action = EncounterAction("Wait", "wait", creature_ref="other")
        >>> CombatRules().action_compatibility(state, "hero", action).failures[0].code
        'wrong_actor'
        """
        return action_compatibility(state, actor_ref, action)

    def reaction_eligibility(
        self,
        state: EncounterState,
        reactor_ref: CreatureRef,
        reaction_kind: str | None = None,
    ) -> ActionEligibility:
        """Return every reason the requested reaction is unavailable.

        >>> from unittest.mock import Mock
        >>> actor = Mock(is_alive=True, reaction_available=False)
        >>> actor.creature.condition_immunities.return_value = frozenset()
        >>> state = Mock(creatures={"hero": actor}, conditions=[], ongoing_effects=[])
        >>> result = CombatRules().reaction_eligibility(state, "hero")
        >>> [failure.code for failure in result.failures]
        ['reaction_spent']
        """
        return reaction_eligibility(state, reactor_ref, reaction_kind)

    def effective_armor_class(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
    ) -> NumericRuleResult:
        """Return base Armor Class plus all sourced adjustments.

        >>> from unittest.mock import Mock
        >>> attributes = Mock(base_armor_class=15, dexterity=14)
        >>> creature = Mock(attributes=attributes, armor_class_modifier_sources={})
        >>> creature.get_modifier.return_value = 2
        >>> state = Mock(creatures={"hero": Mock(creature=creature)}, ongoing_effects=[])
        >>> CombatRules().effective_armor_class(state, "hero").value
        17
        """
        return effective_armor_class(state, creature_ref)

    def effective_speed(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
    ) -> NumericRuleResult:
        """Return Speed after additions, multipliers, and upper caps.

        >>> from unittest.mock import Mock
        >>> movement = Mock(effective_speed_feet=30)
        >>> creature = Mock(speed_modifier_sources={}, attributes=Mock(movement=movement))
        >>> creature.condition_immunities.return_value = frozenset()
        >>> state = Mock(creatures={"hero": Mock(creature=creature)},
        ...     ongoing_effects=[], conditions=[])
        >>> CombatRules().effective_speed(state, "hero").value
        30
        """
        return effective_speed(state, creature_ref)

    def movement_budget(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
    ) -> MovementQueryResult:
        """Translate effective Speed into movement on the encounter grid.

        >>> from unittest.mock import Mock
        >>> from srd_arena.domain.geometry import Grid
        >>> movement = Mock(effective_speed_feet=30)
        >>> creature = Mock(speed_modifier_sources={}, attributes=Mock(movement=movement))
        >>> creature.condition_immunities.return_value = frozenset()
        >>> state = Mock(creatures={"hero": Mock(creature=creature)},
        ...     ongoing_effects=[], conditions=[], definition=Mock(grid=Grid(5, 5)))
        >>> int(CombatRules().movement_budget(state, "hero").budget)
        6
        """
        return movement_budget(state, creature_ref)

    def attack_limit(
        self,
        state: EncounterState,
        creature_ref: CreatureRef,
        base: int,
    ) -> NumericRuleResult:
        """Return the effect-adjusted attack limit for one Attack action.

        >>> from unittest.mock import Mock
        >>> state = Mock(ongoing_effects=[])
        >>> CombatRules().attack_limit(state, "hero", base=3).value
        3
        """
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
        """Collect modifiers matching a particular roll context.

        >>> from unittest.mock import Mock
        >>> creature = Mock(roll_modifier_sources={})
        >>> state = Mock(creatures={"hero": Mock(creature=creature)}, ongoing_effects=[])
        >>> CombatRules().roll_modifiers(state, "hero", "saving_throw").mode
        'normal'
        """
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
        """Collect effects that may prevent an invocation from starting.

        >>> from unittest.mock import Mock
        >>> context = InvocationStartContext("mage", "cast_spell", frozenset({"verbal"}))
        >>> query = CombatRules().invocation_start_checks(Mock(ongoing_effects=[]), context)
        >>> query.failure_chances
        ()
        """
        return invocation_start_checks(state, context)

    def resolve_invocation_start(
        self,
        query: InvocationStartQueryResult,
        roller: DieRoller,
    ) -> InvocationStartResult:
        """Resolve every collected invocation failure chance with a roller.

        >>> from srd_arena.domain.effects.runtime import EffectSource, EffectSourceKind
        >>> from srd_arena.domain.encounters.rule_queries import InvocationFailureChanceContribution
        >>> context = InvocationStartContext("mage", "cast_spell")
        >>> source = EffectSource(EffectSourceKind.SPELL, "slow")
        >>> chance = InvocationFailureChanceContribution(
        ...     "slow:1", source, 1, 4, "slow", "The spell fails.")
        >>> query = InvocationStartQueryResult(context, (chance,))
        >>> CombatRules().resolve_invocation_start(query, lambda _sides: 1).allowed
        False
        """
        return resolve_invocation_start(query, roller)


COMBAT_RULES = CombatRules()
