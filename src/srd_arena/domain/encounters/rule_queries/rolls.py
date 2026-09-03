"""Encounter query for sourced roll modifiers."""

from __future__ import annotations

from srd_arena.domain.effects.condition_rules import effective_conditions
from srd_arena.domain.effects.conditions import CombatTrait
from srd_arena.domain.effects.modifiers import ModifierSubject, RollKind, RollModifier
from srd_arena.domain.effects.rule_effects import RollAdjustment

from ..encounter_models.actions import CreatureRef
from .context import ConditionRuleQueryContext
from .defenses import condition_suppressions
from .models import RollRuleContribution, RollRuleResult
from .providers import ongoing_rule_effects
from .senses import sense_range


def roll_modifiers(
    state: ConditionRuleQueryContext,
    creature_ref: CreatureRef,
    roll: RollKind,
    ability: str | None = None,
    subject: ModifierSubject = "target",
    opposing_ref: CreatureRef | None = None,
) -> RollRuleResult:
    """Return modifiers matching one roll, subject, ability, and opponent.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(ongoing_effects=[], conditions=[])
    >>> result = roll_modifiers(state, "hero", "saving_throw", "wisdom")
    >>> (result.contributions, result.mode)
    ((), 'normal')
    """

    ongoing_contributions = tuple(
        RollRuleContribution(
            provider_state_id,
            source,
            rule_effect.modifier,
        )
        for provider_state_id, source, rule_effect in ongoing_rule_effects(
            state, creature_ref
        )
        if isinstance(rule_effect, RollAdjustment)
        and _modifier_applies(
            state,
            rule_effect.modifier,
            roll=roll,
            ability=ability,
            subject=subject,
            opposing_ref=opposing_ref,
        )
    )
    return RollRuleResult(
        ongoing_contributions
        + _condition_roll_contributions(
            state,
            creature_ref,
            roll=roll,
            ability=ability,
            subject=subject,
        )
    )


def _condition_roll_contributions(
    state: ConditionRuleQueryContext,
    creature_ref: CreatureRef,
    *,
    roll: RollKind,
    ability: str | None,
    subject: ModifierSubject,
) -> tuple[RollRuleContribution, ...]:
    trait_and_modifier = _condition_roll_trait(
        roll=roll,
        ability=ability,
        subject=subject,
    )
    if trait_and_modifier is None:
        return ()
    trait, modifier = trait_and_modifier
    applied_conditions = tuple(
        condition
        for condition in state.conditions
        if condition.target_ref == creature_ref
    )
    conditions = effective_conditions(
        applied_conditions,
        condition_suppressions(state, creature_ref).values,
    )
    providers_by_id = {condition.id: condition for condition in applied_conditions}
    return tuple(
        RollRuleContribution(
            provider_state_id,
            providers_by_id[provider_state_id].identity.source,
            modifier,
        )
        for provider_state_id in conditions.providers_for_trait(trait)
    )


def _condition_roll_trait(
    *,
    roll: RollKind,
    ability: str | None,
    subject: ModifierSubject,
) -> tuple[CombatTrait, RollModifier] | None:
    """Map a roll context to the reusable condition trait that adjusts it."""

    if subject != "target":
        return None
    if roll == "attack_roll":
        return (
            CombatTrait.ATTACK_ROLLS_HAVE_DISADVANTAGE,
            RollModifier("attack_roll", "disadvantage"),
        )
    if roll == "ability_check":
        return (
            CombatTrait.ABILITY_CHECKS_HAVE_DISADVANTAGE,
            RollModifier("ability_check", "disadvantage", ability=ability),
        )
    if roll == "saving_throw" and ability == "dexterity":
        return (
            CombatTrait.DEXTERITY_SAVES_HAVE_DISADVANTAGE,
            RollModifier(
                "saving_throw",
                "disadvantage",
                ability="dexterity",
            ),
        )
    return None


def _modifier_applies(
    state: ConditionRuleQueryContext,
    modifier: RollModifier,
    *,
    roll: RollKind,
    ability: str | None,
    subject: ModifierSubject,
    opposing_ref: CreatureRef | None,
) -> bool:
    if modifier.roll != roll or modifier.subject != subject:
        return False
    if modifier.ability is not None and modifier.ability != ability:
        return False
    if opposing_ref is None or not modifier.ignored_by_senses:
        return True
    return not any(
        sense_range(state, opposing_ref, sense).range_feet is not None
        for sense in modifier.ignored_by_senses
    )
