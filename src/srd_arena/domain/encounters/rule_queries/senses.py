"""Encounter queries for intrinsic and effect-granted senses."""

from __future__ import annotations

from ...effects.rule_effects import GrantedSense
from .context import CreatureEffectQueryContext
from .models import SenseRuleResult, SourcedRuleContribution
from .providers import ongoing_rule_effects


def sense_range(
    state: CreatureEffectQueryContext,
    creature_ref: str,
    sense: str,
) -> SenseRuleResult:
    """Return the longest intrinsic or effect-granted range for a sense.

    >>> from types import SimpleNamespace
    >>> from ...effects.runtime import EffectSource, EffectSourceKind
    >>> creature = SimpleNamespace(sense_range=lambda name: 30)
    >>> source = EffectSource(EffectSourceKind.SPELL, "true_seeing")
    >>> effect = SimpleNamespace(
    ...     identity=SimpleNamespace(id="effect-1", source=source),
    ...     target_refs=("hero",),
    ...     rule_effects=(GrantedSense("truesight", 120),),
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={"hero": SimpleNamespace(creature=creature)},
    ...     ongoing_effects=[effect],
    ... )
    >>> result = sense_range(state, "hero", "Truesight")
    >>> (result.range_feet, result.contributions[0].source.definition_id)
    (120, 'true_seeing')
    """

    creature = state.creatures[creature_ref].creature
    normalized = sense.casefold()
    contributions = tuple(
        SourcedRuleContribution(
            provider_state_id,
            source,
            rule_effect.range_feet,
        )
        for provider_state_id, source, rule_effect in ongoing_rule_effects(
            state, creature_ref
        )
        if isinstance(rule_effect, GrantedSense) and rule_effect.sense == normalized
    )
    return SenseRuleResult(creature.sense_range(normalized), contributions)
