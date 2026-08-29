"""Encounter queries and mutations for effect-adjusted hit points."""

from __future__ import annotations

from srd_arena.domain.effects.rule_effects import MaximumHitPointAdjustment
from srd_arena.domain.effects.runtime import EffectSource

from .context import CreatureEffectQueryContext
from .models import NumericOperation, NumericRuleContribution, NumericRuleResult


def effective_maximum_health(
    state: CreatureEffectQueryContext,
    creature_ref: str,
) -> NumericRuleResult:
    """Return intrinsic maximum HP plus the strongest instance of each rule.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(get_max_health=lambda: 10)
    >>> state = SimpleNamespace(
    ...     creatures={"hero": SimpleNamespace(creature=creature)},
    ...     ongoing_effects=[],
    ... )
    >>> effective_maximum_health(state, "hero").value
    10
    """

    grouped: dict[
        str,
        tuple[str, EffectSource, MaximumHitPointAdjustment],
    ] = {}
    for effect in state.ongoing_effects:
        if creature_ref not in effect.target_refs:
            continue
        for rule_effect in effect.rule_effects:
            if not isinstance(rule_effect, MaximumHitPointAdjustment):
                continue
            definition_id = effect.identity.source.definition_id
            current = grouped.get(definition_id)
            if current is None or rule_effect.value > current[2].value:
                grouped[definition_id] = (
                    effect.identity.id,
                    effect.identity.source,
                    rule_effect,
                )
    contributions = tuple(
        NumericRuleContribution(
            provider_state_id,
            source,
            NumericOperation.ADD,
            adjustment.value,
        )
        for provider_state_id, source, adjustment in grouped.values()
    )
    creature = state.creatures[creature_ref].creature
    return NumericRuleResult(creature.get_max_health(), contributions, minimum=0)


def apply_healing(
    state: CreatureEffectQueryContext,
    creature_ref: str,
    amount: int,
) -> int:
    """Heal a creature without exceeding its effect-adjusted maximum HP."""

    creature = state.creatures[creature_ref].creature
    maximum = effective_maximum_health(state, creature_ref).value
    return creature.heal(amount, maximum_health=maximum)
