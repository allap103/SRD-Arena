"""Query source-bound damage added to successful attack rolls."""

from srd_arena.domain.capabilities import DamageEffect
from srd_arena.domain.creatures.feature_rules import (
    FRENZY_FEATURE_ID,
    frenzy_attack_hit_damage,
)
from srd_arena.domain.effects.rule_effects import AttackHitDamage
from srd_arena.domain.effects.runtime import EffectSource, EffectSourceKind

from .context import CreatureEffectQueryContext
from .models import SourcedRuleContribution


def attack_hit_damage(
    state: CreatureEffectQueryContext,
    attacker_ref: str,
    target_ref: str,
    *,
    attack_ability: str | None = None,
    attack_damage_type: str | None = None,
    excluded_feature_ids: frozenset[str] = frozenset(),
) -> tuple[SourcedRuleContribution[DamageEffect], ...]:
    """Return target-bound and intrinsic riders for one prospective attack hit."""

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
    if attack_damage_type is not None:
        attacker_effect_ids = {
            ongoing.identity.source.definition_id
            for ongoing in state.ongoing_effects
            if attacker_ref in ongoing.target_refs
        }
        frenzy = frenzy_attack_hit_damage(
            state.creatures[attacker_ref].creature,
            attacker_effect_ids,
            attack_ability,
            attack_damage_type,
            excluded_feature_ids,
        )
        if frenzy is not None:
            contributions.append(
                SourcedRuleContribution(
                    f"intrinsic:{attacker_ref}:{FRENZY_FEATURE_ID}",
                    EffectSource(
                        EffectSourceKind.FEATURE,
                        FRENZY_FEATURE_ID,
                        applied_by_ref=attacker_ref,
                        label="Frenzy",
                    ),
                    frenzy,
                )
            )
    return tuple(contributions)
