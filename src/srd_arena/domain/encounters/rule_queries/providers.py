"""Locate runtime rule effects and their provenance."""

from __future__ import annotations

from collections.abc import Iterator

from srd_arena.domain.effects.rule_effects import RuntimeRuleEffect
from srd_arena.domain.effects.runtime import EffectSource

from ..encounter_models.actions import CreatureRef
from .context import CreatureEffectQueryContext, EffectQueryContext


def creature_rule_effects(
    state: CreatureEffectQueryContext,
    creature_ref: CreatureRef,
) -> Iterator[tuple[str, EffectSource, RuntimeRuleEffect]]:
    """Yield intrinsic and temporary rule effects affecting one creature."""

    creature = state.creatures[creature_ref].creature
    for provider in creature.combat_profile.intrinsic_rule_providers.values():
        if (
            provider.blocked_by_armor_categories
            and creature.worn_armor_category(state.item_templates)
            in provider.blocked_by_armor_categories
        ):
            continue
        source = EffectSource(
            provider.source_kind,
            provider.id,
            applied_by_ref=creature_ref,
            label=provider.label,
        )
        provider_id = f"intrinsic:{creature_ref}:{provider.id}"
        for rule_effect in provider.rule_effects:
            yield provider_id, source, rule_effect
    yield from ongoing_rule_effects(state, creature_ref)


def ongoing_rule_effects(
    state: EffectQueryContext,
    creature_ref: CreatureRef,
) -> Iterator[tuple[str, EffectSource, RuntimeRuleEffect]]:
    """Yield active typed rule effects, once per authored definition.

    Multiple instances retain independent duration and provenance, but effects
    from the same named rule do not stack.  When the active instance ends, the
    next instance becomes the provider automatically.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.effects.rule_effects import ArmorClassAdjustment
    >>> from srd_arena.domain.effects.runtime import EffectSource, EffectSourceKind
    >>> source = EffectSource(EffectSourceKind.SPELL, "shield")
    >>> ongoing = SimpleNamespace(
    ...     identity=SimpleNamespace(id="effect-1", source=source),
    ...     target_refs=("hero",), rule_effects=(ArmorClassAdjustment(5),),
    ... )
    >>> [(state_id, effect.value) for state_id, _source, effect in
    ...  ongoing_rule_effects(SimpleNamespace(ongoing_effects=[ongoing]), "hero")]
    [('effect-1', 5)]
    """

    active_definitions: set[str] = set()
    for ongoing in state.ongoing_effects:
        definition_id = ongoing.identity.source.definition_id
        if (
            creature_ref not in ongoing.target_refs
            or not ongoing.rule_effects
            or definition_id in active_definitions
        ):
            continue
        active_definitions.add(definition_id)
        for rule_effect in ongoing.rule_effects:
            yield ongoing.identity.id, ongoing.identity.source, rule_effect
