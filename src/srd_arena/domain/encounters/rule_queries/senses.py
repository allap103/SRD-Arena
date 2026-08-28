"""Encounter queries for intrinsic and effect-granted senses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...effects.rule_effects import GrantedSense
from .models import SenseRuleResult, SourcedRuleContribution
from .providers import ongoing_rule_effects

if TYPE_CHECKING:
    from ..encounter import EncounterState


def sense_range(
    state: EncounterState,
    creature_ref: str,
    sense: str,
) -> SenseRuleResult:
    """Return the longest intrinsic or effect-granted range for a sense."""

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
