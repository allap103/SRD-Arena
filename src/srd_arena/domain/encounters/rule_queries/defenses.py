"""Encounter queries and mutations for temporary defensive effects."""

from __future__ import annotations

from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.rule_effects import (
    ConditionImmunity,
    ConditionSaveAdvantage,
    ConditionSuppression,
    DamageReduction,
    DamageResistance,
)
from srd_arena.domain.rolls.dice import DieRoller

from .context import (
    CreatureEffectQueryContext,
    DamageRuleQueryContext,
    EffectQueryContext,
)
from .models import SetRuleResult, SourcedRuleContribution
from .providers import ongoing_rule_effects


def condition_immunities(
    state: CreatureEffectQueryContext,
    creature_ref: str,
) -> SetRuleResult[Condition]:
    """Return intrinsic and effect-granted condition immunities."""

    creature = state.creatures[creature_ref].creature
    contributions = tuple(
        SourcedRuleContribution(
            provider_state_id,
            source,
            rule_effect.conditions,
        )
        for provider_state_id, source, rule_effect in ongoing_rule_effects(
            state, creature_ref
        )
        if isinstance(rule_effect, ConditionImmunity)
    )
    return SetRuleResult(creature.statistics.condition_immunities, contributions)


def damage_resistances(
    state: CreatureEffectQueryContext,
    creature_ref: str,
) -> SetRuleResult[str]:
    """Return intrinsic and effect-granted damage resistances."""

    creature = state.creatures[creature_ref].creature
    contributions = tuple(
        SourcedRuleContribution(
            provider_state_id,
            source,
            rule_effect.damage_types,
        )
        for provider_state_id, source, rule_effect in ongoing_rule_effects(
            state, creature_ref
        )
        if isinstance(rule_effect, DamageResistance)
    )
    return SetRuleResult(creature.statistics.damage_resistances, contributions)


def condition_suppressions(
    state: EffectQueryContext,
    creature_ref: str,
) -> SetRuleResult[Condition]:
    """Return conditions suspended by active effects without removing them.

    The result preserves the runtime effect and authored source that supplied
    each suppression, so callers can explain why a condition is inactive.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.effects.runtime import EffectSource, EffectSourceKind
    >>> source = EffectSource(EffectSourceKind.SPELL, "calm_emotions")
    >>> effect = SimpleNamespace(
    ...     identity=SimpleNamespace(id="effect-1", source=source),
    ...     target_refs=("hero",),
    ...     rule_effects=(ConditionSuppression(frozenset({Condition.CHARMED})),),
    ... )
    >>> result = condition_suppressions(
    ...     SimpleNamespace(ongoing_effects=[effect]), "hero"
    ... )
    >>> (Condition.CHARMED in result.values, result.contributions[0].provider_state_id)
    (True, 'effect-1')
    """

    contributions = tuple(
        SourcedRuleContribution(
            provider_state_id,
            source,
            rule_effect.conditions,
        )
        for provider_state_id, source, rule_effect in ongoing_rule_effects(
            state, creature_ref
        )
        if isinstance(rule_effect, ConditionSuppression)
    )
    return SetRuleResult(frozenset(), contributions)


def has_condition_save_advantage(
    state: EffectQueryContext,
    creature_ref: str,
    conditions: tuple[str, ...],
) -> bool:
    """Return whether an active effect helps a save against listed conditions.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(ongoing_effects=[])
    >>> has_condition_save_advantage(state, "hero", ("poisoned",))
    False
    """

    requested = {condition.casefold() for condition in conditions}
    if not requested:
        return False
    return any(
        bool(
            requested.intersection(
                condition.value for condition in rule_effect.conditions
            )
        )
        for _provider_state_id, _source, rule_effect in ongoing_rule_effects(
            state, creature_ref
        )
        if isinstance(rule_effect, ConditionSaveAdvantage)
    )


def resolve_damage_reduction(
    state: EffectQueryContext,
    creature_ref: str,
    damage_type: str,
    roller: DieRoller,
) -> int:
    """Resolve and consume matching once-per-turn reduction contributions."""

    normalized = damage_type.casefold()
    return sum(
        rule_effect.resolve(roller)
        for _provider_state_id, _source, rule_effect in ongoing_rule_effects(
            state, creature_ref
        )
        if isinstance(rule_effect, DamageReduction)
        and rule_effect.damage_type == normalized
    )


def apply_damage(
    state: DamageRuleQueryContext,
    creature_ref: str,
    amount: int,
    damage_type: str | None = None,
) -> int:
    """Apply reduction and resistance before mutating creature health."""

    if damage_type is not None:
        amount = max(
            0,
            amount
            - resolve_damage_reduction(
                state,
                creature_ref,
                damage_type,
                state.dice.roll_die,
            ),
        )
        if damage_type.casefold() in damage_resistances(state, creature_ref).values:
            amount //= 2
    return state.creatures[creature_ref].creature.take_damage(amount)


def reset_damage_reductions(
    state: EffectQueryContext,
    creature_ref: str,
) -> None:
    """Restore every active once-per-turn reduction for one creature."""

    for _provider_state_id, _source, rule_effect in ongoing_rule_effects(
        state, creature_ref
    ):
        if isinstance(rule_effect, DamageReduction):
            rule_effect.available = True
