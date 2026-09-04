"""Query source-bound damage added to successful attack rolls."""

from srd_arena.domain.capabilities import DamageEffect
from srd_arena.domain.effects.rule_effects import AttackHitDamage

from .context import EffectQueryContext
from .models import SourcedRuleContribution


def attack_hit_damage(
    state: EffectQueryContext,
    attacker_ref: str,
    target_ref: str,
) -> tuple[SourcedRuleContribution[DamageEffect], ...]:
    """Return persistent damage riders bound to this attacker and target."""

    contributions: list[SourcedRuleContribution[DamageEffect]] = []
    active_definitions: set[str] = set()
    for ongoing in state.ongoing_effects:
        source = ongoing.identity.source
        if (
            target_ref not in ongoing.target_refs
            or source.applied_by_ref != attacker_ref
            or source.definition_id in active_definitions
        ):
            continue
        matching = tuple(
            rule_effect
            for rule_effect in ongoing.rule_effects
            if isinstance(rule_effect, AttackHitDamage)
        )
        if not matching:
            continue
        active_definitions.add(source.definition_id)
        contributions.extend(
            SourcedRuleContribution(
                ongoing.identity.id,
                source,
                DamageEffect(rule_effect.dice, 0, rule_effect.damage_type),
            )
            for rule_effect in matching
        )
    return tuple(contributions)
