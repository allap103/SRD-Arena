"""Locate runtime rule effects and their provenance."""

from __future__ import annotations

from collections.abc import Iterator

from ...effects.rule_effects import RuntimeRuleEffect
from ...effects.runtime import EffectSource
from ..encounter_models.actions import CreatureRef
from .context import EffectQueryContext


def ongoing_rule_effects(
    state: EffectQueryContext,
    creature_ref: CreatureRef,
) -> Iterator[tuple[str, EffectSource, RuntimeRuleEffect]]:
    """Yield active typed rule effects, once per authored definition.

    Multiple instances retain independent duration and provenance, but effects
    from the same named rule do not stack.  When the active instance ends, the
    next instance becomes the provider automatically.

    >>> from types import SimpleNamespace
    >>> from ...effects.rule_effects import ArmorClassAdjustment
    >>> from ...effects.runtime import EffectSource, EffectSourceKind
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
