"""Encounter query for sourced roll modifiers."""

from __future__ import annotations

from srd_arena.domain.effects.modifiers import ModifierSubject, RollKind, RollModifier
from srd_arena.domain.effects.rule_effects import RollAdjustment

from ..encounter_models.actions import CreatureRef
from .context import CreatureEffectQueryContext
from .models import RollRuleContribution, RollRuleResult
from .providers import ongoing_rule_effects
from .senses import sense_range


def roll_modifiers(
    state: CreatureEffectQueryContext,
    creature_ref: CreatureRef,
    roll: RollKind,
    ability: str | None = None,
    subject: ModifierSubject = "target",
    opposing_ref: CreatureRef | None = None,
) -> RollRuleResult:
    """Return modifiers matching one roll, subject, ability, and opponent.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(ongoing_effects=[])
    >>> result = roll_modifiers(state, "hero", "saving_throw", "wisdom")
    >>> (result.contributions, result.mode)
    ((), 'normal')
    """

    contributions = tuple(
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
    return RollRuleResult(contributions)


def _modifier_applies(
    state: CreatureEffectQueryContext,
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
