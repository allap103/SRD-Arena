"""Query sourced damage that retaliates against successful attack rolls."""

from srd_arena.domain.effects.rule_effects import AttackHitRetaliation

from .context import CreatureEffectQueryContext
from .models import SourcedRuleContribution


def attack_hit_retaliations(
    state: CreatureEffectQueryContext,
    target_ref: str,
    attack_type: str,
) -> tuple[SourcedRuleContribution[AttackHitRetaliation], ...]:
    """Return active retaliation rules protecting a target from this attack type.

    The caller queries before applying the triggering hit. This preserves the
    rule when that same hit depletes the temporary Hit Points that gated it.
    """

    target = state.creatures[target_ref].creature
    normalized_attack_type = attack_type.casefold()
    return tuple(
        SourcedRuleContribution(
            ongoing.identity.id,
            ongoing.identity.source,
            rule_effect,
        )
        for ongoing in state.ongoing_effects
        if target_ref in ongoing.target_refs
        for rule_effect in ongoing.rule_effects
        if isinstance(rule_effect, AttackHitRetaliation)
        and normalized_attack_type in rule_effect.attack_types
        and (
            not rule_effect.requires_temporary_hit_points
            or target.temporary_hit_points > 0
        )
    )
