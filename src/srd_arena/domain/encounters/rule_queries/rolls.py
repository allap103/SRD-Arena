"""Encounter query for sourced roll modifiers."""

from __future__ import annotations

from srd_arena.domain.effects.condition_rules import effective_conditions
from srd_arena.domain.effects.conditions import CombatTrait, Condition
from srd_arena.domain.effects.modifiers import ModifierSubject, RollKind, RollModifier
from srd_arena.domain.effects.rule_effects import (
    AdjacentAllyAttackAdvantage,
    RollAdjustment,
)

from ..encounter_models.actions import CreatureRef
from ..spatial import creature_distance
from .context import ConditionRuleQueryContext
from .defenses import condition_suppressions
from .models import RollRuleContribution, RollRuleResult
from .providers import creature_rule_effects
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
    >>> profile = SimpleNamespace(intrinsic_rule_providers={})
    >>> creature = SimpleNamespace(combat_profile=profile)
    >>> state = SimpleNamespace(ongoing_effects=[], conditions=[],
    ...     creatures={"hero": SimpleNamespace(creature=creature)})
    >>> result = roll_modifiers(state, "hero", "saving_throw", "wisdom")
    >>> (result.contributions, result.mode)
    ((), 'normal')
    """

    rule_contributions = _rule_effect_contributions(
        state,
        creature_ref,
        roll=roll,
        ability=ability,
        subject=subject,
        opposing_ref=opposing_ref,
    )
    return RollRuleResult(
        rule_contributions
        + _condition_roll_contributions(
            state,
            creature_ref,
            roll=roll,
            ability=ability,
            subject=subject,
        )
    )


def _rule_effect_contributions(
    state: ConditionRuleQueryContext,
    creature_ref: CreatureRef,
    *,
    roll: RollKind,
    ability: str | None,
    subject: ModifierSubject,
    opposing_ref: CreatureRef | None,
) -> tuple[RollRuleContribution, ...]:
    contributions: list[RollRuleContribution] = []
    for provider_state_id, source, rule_effect in creature_rule_effects(
        state, creature_ref
    ):
        modifier: RollModifier | None = None
        if isinstance(rule_effect, RollAdjustment):
            if not _roll_adjustment_is_blocked(state, creature_ref, rule_effect):
                modifier = rule_effect.modifier
        elif (
            isinstance(rule_effect, AdjacentAllyAttackAdvantage)
            and roll == "attack_roll"
            and subject == "target"
            and opposing_ref is not None
            and _has_eligible_ally_near_target(
                state,
                creature_ref,
                opposing_ref,
                rule_effect.range_feet,
            )
        ):
            modifier = RollModifier("attack_roll", "advantage")
        if modifier is not None and _modifier_applies(
            state,
            modifier,
            roll=roll,
            ability=ability,
            subject=subject,
            opposing_ref=opposing_ref,
        ):
            contributions.append(
                RollRuleContribution(provider_state_id, source, modifier)
            )
    return tuple(contributions)


def _has_eligible_ally_near_target(
    state: ConditionRuleQueryContext,
    attacker_ref: CreatureRef,
    target_ref: CreatureRef,
    range_feet: int,
) -> bool:
    attacker_team = _creature_team_id(state, attacker_ref)
    for ally_ref, ally in state.creatures.items():
        if (
            ally_ref == attacker_ref
            or not ally.is_alive
            or _creature_team_id(state, ally_ref) != attacker_team
            or _has_effective_condition(state, ally_ref, Condition.INCAPACITATED)
        ):
            continue
        distance = creature_distance(state, ally_ref, target_ref)
        if state.definition.grid.feet_for_squares(distance) <= range_feet:
            return True
    return False


def _creature_team_id(
    state: ConditionRuleQueryContext,
    creature_ref: CreatureRef,
) -> str:
    creature_id = state.creatures[creature_ref].creature_id
    team = next(
        (team for team in state.definition.teams if creature_id in team.members),
        None,
    )
    return team.id if team is not None else creature_id


def _has_effective_condition(
    state: ConditionRuleQueryContext,
    creature_ref: CreatureRef,
    condition: Condition,
) -> bool:
    applied = tuple(
        existing for existing in state.conditions if existing.target_ref == creature_ref
    )
    suppressions = condition_suppressions(state, creature_ref).values
    return effective_conditions(applied, suppressions).has(condition)


def _roll_adjustment_is_blocked(
    state: ConditionRuleQueryContext,
    creature_ref: CreatureRef,
    adjustment: RollAdjustment,
) -> bool:
    if not adjustment.blocked_by_conditions:
        return False
    applied_conditions = tuple(
        condition
        for condition in state.conditions
        if condition.target_ref == creature_ref
    )
    conditions = effective_conditions(
        applied_conditions,
        condition_suppressions(state, creature_ref).values,
    )
    return any(
        conditions.has(condition) for condition in adjustment.blocked_by_conditions
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
