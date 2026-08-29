"""Encounter queries evaluated immediately before invocation resolution."""

from __future__ import annotations

from ...effects.rule_effects import InvocationFailureChance
from ...rolls.dice import DieRoller
from .context import EffectQueryContext
from .models import (
    InvocationFailureChanceContribution,
    InvocationStartContext,
    InvocationStartQueryResult,
    InvocationStartResult,
    InvocationStartRoll,
)
from .providers import ongoing_rule_effects


def invocation_start_checks(
    state: EffectQueryContext,
    context: InvocationStartContext,
) -> InvocationStartQueryResult:
    """Collect sourced failure chances matching invocation kind and components.

    >>> from types import SimpleNamespace
    >>> from ...effects.runtime import EffectSource, EffectSourceKind
    >>> source = EffectSource(EffectSourceKind.SPELL, "slow")
    >>> chance = InvocationFailureChance(
    ...     frozenset({"cast_spell"}), frozenset({"somatic"}),
    ...     1, 4, "slow.failure", "The gestures are too slow.",
    ... )
    >>> ongoing = SimpleNamespace(
    ...     identity=SimpleNamespace(id="slow-1", source=source),
    ...     target_refs=("mage",), rule_effects=(chance,),
    ... )
    >>> context = InvocationStartContext(
    ...     "mage", "cast_spell", frozenset({"somatic", "verbal"})
    ... )
    >>> query = invocation_start_checks(
    ...     SimpleNamespace(ongoing_effects=[ongoing]), context
    ... )
    >>> query.failure_chances[0].provider_state_id
    'slow-1'
    """

    invocation_kind = context.kind.casefold()
    components = frozenset(component.casefold() for component in context.components)
    failure_chances = tuple(
        InvocationFailureChanceContribution(
            provider_state_id=provider_state_id,
            source=source,
            numerator=rule_effect.numerator,
            denominator=rule_effect.denominator,
            code=rule_effect.code,
            message=rule_effect.message,
        )
        for provider_state_id, source, rule_effect in ongoing_rule_effects(
            state, context.actor_ref
        )
        if isinstance(rule_effect, InvocationFailureChance)
        and (
            not rule_effect.invocation_kinds
            or invocation_kind
            in {candidate.casefold() for candidate in rule_effect.invocation_kinds}
        )
        and {
            required.casefold() for required in rule_effect.required_components
        }.issubset(components)
    )
    return InvocationStartQueryResult(context, failure_chances)


def resolve_invocation_start(
    query: InvocationStartQueryResult,
    roller: DieRoller,
) -> InvocationStartResult:
    """Roll every applicable failure chance and retain complete roll details.

    >>> from ...effects.runtime import EffectSource, EffectSourceKind
    >>> source = EffectSource(EffectSourceKind.SPELL, "slow")
    >>> chance = InvocationFailureChanceContribution(
    ...     "slow-1", source, 1, 4, "slow.failure", "Too slow."
    ... )
    >>> query = InvocationStartQueryResult(
    ...     InvocationStartContext("mage", "cast_spell"), (chance,)
    ... )
    >>> result = resolve_invocation_start(query, lambda sides: 1)
    >>> (result.allowed, result.failures[0].code)
    (False, 'slow.failure')
    """

    rolls = tuple(
        _resolve_failure_chance(contribution, roller)
        for contribution in query.failure_chances
    )
    return InvocationStartResult(query.context, rolls)


def _resolve_failure_chance(
    contribution: InvocationFailureChanceContribution,
    roller: DieRoller,
) -> InvocationStartRoll:
    roll = roller(contribution.denominator)
    return InvocationStartRoll(
        contribution=contribution,
        roll=roll,
        failed=roll <= contribution.numerator,
    )
