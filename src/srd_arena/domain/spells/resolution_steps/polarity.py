"""Classify ongoing spell state without leaking rule details into frontends."""

from srd_arena.domain.capabilities import (
    ArmorClassModifierEffect,
    ConditionImmunityEffect,
    ConditionSaveAdvantageEffect,
    DamageImmunityEffect,
    DamageReductionEffect,
    DamageResistanceEffect,
    HitPointMaximumModifierEffect,
    ProhibitReactionsEffect,
    RollModifierEffect,
    SenseEffect,
    SpeedModifierEffect,
    SpeedMultiplierEffect,
    TemporaryHitPointsEffect,
    TurnEconomyRestrictionEffect,
)
from srd_arena.domain.effects.runtime import EffectPolarity

from .preparation import PreparedSpellResolution

_BENEFICIAL_CONDITIONS = frozenset({"invisible"})


def persistent_spell_effect_polarity(
    prepared: PreparedSpellResolution,
) -> EffectPolarity:
    """Classify the persistent part of one resolved spell.

    >>> from types import SimpleNamespace
    >>> prepared = SimpleNamespace(
    ...     repeat_failure_damage=(), conditions=(),
    ...     repeat_failure_conditions=(),
    ...     definition_effects=(ArmorClassModifierEffect(2),),
    ...     definition=SimpleNamespace(
    ...         target=SimpleNamespace(disposition="any")
    ...     ),
    ... )
    >>> persistent_spell_effect_polarity(prepared)
    <EffectPolarity.BENEFICIAL: 'beneficial'>
    """

    beneficial = False
    harmful = bool(prepared.repeat_failure_damage)
    for condition in (
        *prepared.conditions,
        *prepared.repeat_failure_conditions,
    ):
        if condition in _BENEFICIAL_CONDITIONS:
            beneficial = True
        else:
            harmful = True
    for effect in prepared.definition_effects:
        if isinstance(effect, ArmorClassModifierEffect):
            beneficial |= effect.value > 0
            harmful |= effect.value < 0
        elif isinstance(effect, SpeedModifierEffect):
            beneficial |= effect.feet > 0
            harmful |= effect.feet < 0
        elif isinstance(effect, SpeedMultiplierEffect):
            beneficial |= effect.numerator > effect.denominator
            harmful |= effect.numerator < effect.denominator
        elif isinstance(effect, HitPointMaximumModifierEffect):
            beneficial |= effect.value > 0
            harmful |= effect.value < 0
        elif isinstance(effect, RollModifierEffect):
            modifier_polarity = _roll_modifier_polarity(effect)
            beneficial |= modifier_polarity is EffectPolarity.BENEFICIAL
            harmful |= modifier_polarity is EffectPolarity.HARMFUL
        elif isinstance(
            effect,
            (
                ConditionImmunityEffect,
                ConditionSaveAdvantageEffect,
                DamageImmunityEffect,
                DamageReductionEffect,
                DamageResistanceEffect,
                SenseEffect,
                TemporaryHitPointsEffect,
            ),
        ):
            beneficial = True
        elif isinstance(
            effect,
            (ProhibitReactionsEffect, TurnEconomyRestrictionEffect),
        ):
            harmful = True

    if beneficial and harmful:
        return EffectPolarity.NEUTRAL
    if beneficial:
        return EffectPolarity.BENEFICIAL
    if harmful:
        return EffectPolarity.HARMFUL

    disposition = prepared.definition.target.disposition
    if disposition in {"ally", "source", "willing"}:
        return EffectPolarity.BENEFICIAL
    if disposition == "enemy":
        return EffectPolarity.HARMFUL
    return EffectPolarity.NEUTRAL


def _roll_modifier_polarity(effect: RollModifierEffect) -> EffectPolarity:
    beneficial = effect.mode in {"add", "advantage"}
    harmful = effect.mode in {"subtract", "disadvantage"}
    if effect.subject == "attacks_against_target":
        beneficial, harmful = harmful, beneficial
    if beneficial == harmful:
        return EffectPolarity.NEUTRAL
    return EffectPolarity.BENEFICIAL if beneficial else EffectPolarity.HARMFUL
