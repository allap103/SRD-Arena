"""Build provider-neutral domain effects from spell-authored effects."""

import srd_arena.content.spells.resolution as spell_effects
import srd_arena.domain.capabilities as domain
from srd_arena.content.capabilities.builder import (
    build_duration,
    build_effect,
    is_shared_effect,
)

_SPELL_EFFECT_TYPES = (
    spell_effects.HealingEffectSchema,
    spell_effects.TemporaryHitPointsEffectSchema,
    spell_effects.ArmorClassModifierEffectSchema,
    spell_effects.RemoveEffectSchema,
    spell_effects.DamageResistanceEffectSchema,
    spell_effects.DamageReductionEffectSchema,
    spell_effects.SpeedModifierEffectSchema,
    spell_effects.ConditionSaveAdvantageEffectSchema,
    spell_effects.DamageImmunityEffectSchema,
    spell_effects.ConditionImmunityEffectSchema,
    spell_effects.SenseEffectSchema,
    spell_effects.HitPointMaximumModifierEffectSchema,
)


def is_buildable_effect(value: object) -> bool:
    """Return whether an authored effect has a shared domain representation.

    >>> healing = spell_effects.HealingEffectSchema(type="healing", dice="1d8")
    >>> is_buildable_effect(healing)
    True
    >>> is_buildable_effect(object())
    False
    """
    return is_shared_effect(value) or isinstance(value, _SPELL_EFFECT_TYPES)


def build_capability_effect(value: object) -> domain.CapabilityEffect:
    """Build a shared domain effect from an authored action or spell effect.

    >>> schema = spell_effects.HealingEffectSchema(
    ...     type="healing", dice="1d8", modifier="spellcasting_ability")
    >>> effect = build_capability_effect(schema)
    >>> (effect.dice, effect.modifier)
    ('1d8', 'ability_modifier')
    """
    if is_shared_effect(value):
        return build_effect(value)
    if isinstance(value, spell_effects.HealingEffectSchema):
        return domain.HealingEffect(
            dice=value.dice,
            bonus=value.bonus,
            modifier=(
                "ability_modifier"
                if value.modifier == "spellcasting_ability"
                else "none"
            ),
            from_damage=value.from_damage,
            restore_to_maximum=value.restore_to_maximum,
            pool=value.pool,
        )
    if isinstance(value, spell_effects.TemporaryHitPointsEffectSchema):
        return domain.TemporaryHitPointsEffect(
            dice=value.dice,
            value=value.value,
            modifier=(
                "ability_modifier"
                if value.modifier == "spellcasting_ability"
                else "none"
            ),
            trigger=value.trigger,
        )
    if isinstance(value, spell_effects.ArmorClassModifierEffectSchema):
        return domain.ArmorClassModifierEffect(
            value.value,
            build_duration(value.duration),
        )
    if isinstance(value, spell_effects.RemoveEffectSchema):
        return domain.RemoveEffect(
            removable=tuple(value.removable),
            selection=value.selection,
            conditions=tuple(value.conditions),
        )
    if isinstance(value, spell_effects.DamageResistanceEffectSchema):
        return domain.DamageResistanceEffect(
            tuple(value.damage_types),
            value.selection,
            build_duration(value.duration),
        )
    if isinstance(value, spell_effects.DamageReductionEffectSchema):
        return domain.DamageReductionEffect(
            damage_types=tuple(value.damage_types),
            dice=value.dice,
            selection=value.selection,
            limit=value.limit,
            period=value.period,
            duration=build_duration(value.duration),
        )
    if isinstance(value, spell_effects.SpeedModifierEffectSchema):
        return domain.SpeedModifierEffect(
            value.feet,
            build_duration(value.duration),
        )
    if isinstance(value, spell_effects.ConditionSaveAdvantageEffectSchema):
        return domain.ConditionSaveAdvantageEffect(
            tuple(value.conditions),
            build_duration(value.duration),
        )
    if isinstance(value, spell_effects.DamageImmunityEffectSchema):
        return domain.DamageImmunityEffect(
            tuple(value.damage_types),
            build_duration(value.duration),
        )
    if isinstance(value, spell_effects.ConditionImmunityEffectSchema):
        return domain.ConditionImmunityEffect(
            tuple(value.conditions),
            value.suppress_existing,
            build_duration(value.duration),
        )
    if isinstance(value, spell_effects.SenseEffectSchema):
        return domain.SenseEffect(
            value.sense,
            value.range_feet,
            build_duration(value.duration),
        )
    if isinstance(value, spell_effects.HitPointMaximumModifierEffectSchema):
        return domain.HitPointMaximumModifierEffect(
            value.value,
            value.also_modify_current,
            build_duration(value.duration),
        )
    raise TypeError(f"Unsupported capability effect: {type(value).__name__}")
