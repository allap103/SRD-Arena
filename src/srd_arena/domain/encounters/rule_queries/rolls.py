"""Encounter query for sourced roll modifiers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...effects.modifiers import ModifierSubject, RollKind, RollModifier
from ...effects.rule_effects import RollAdjustment
from ..models import CreatureRef
from .models import RollRuleContribution, RollRuleResult
from .providers import legacy_modifier_provider, ongoing_rule_effects

if TYPE_CHECKING:
    from ..encounter import EncounterState


def roll_modifiers(
    state: EncounterState,
    creature_ref: CreatureRef,
    roll: RollKind,
    ability: str | None = None,
    subject: ModifierSubject = "target",
    opposing_ref: CreatureRef | None = None,
) -> RollRuleResult:
    """Return modifiers matching one roll, subject, ability, and opponent.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(roll_modifier_sources={})
    >>> state = SimpleNamespace(
    ...     creatures={"hero": SimpleNamespace(creature=creature)},
    ...     ongoing_effects=[],
    ... )
    >>> result = roll_modifiers(state, "hero", "saving_throw", "wisdom")
    >>> (result.contributions, result.mode)
    ((), 'normal')
    """

    creature = state.creatures[creature_ref].creature
    contributions: list[RollRuleContribution] = []
    for definition_id, sources in creature.roll_modifier_sources.items():
        if not sources:
            continue
        origin_id, modifiers = next(iter(sources.items()))
        provider_state_id, source = legacy_modifier_provider(
            state,
            creature_ref,
            definition_id,
            origin_id,
        )
        contributions.extend(
            RollRuleContribution(provider_state_id, source, modifier)
            for modifier in modifiers
            if _modifier_applies(
                state,
                modifier,
                roll=roll,
                ability=ability,
                subject=subject,
                opposing_ref=opposing_ref,
            )
        )
    contributions.extend(
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
    return RollRuleResult(tuple(contributions))


def _modifier_applies(
    state: EncounterState,
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
    opposing = state.creatures[opposing_ref].creature
    return not any(opposing.has_sense(sense) for sense in modifier.ignored_by_senses)
