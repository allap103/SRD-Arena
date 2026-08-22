"""Compile spell-authored effects into provider-neutral domain effects."""

from srd_arena.content.capabilities.compiler import (
    compile_duration,
    compile_effect,
    is_shared_effect,
)
from srd_arena.content.spells import resolution as spell_effects
import srd_arena.domain.capabilities as domain


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


def is_compilable_effect(value: object) -> bool:
    """Return whether an authored effect has a shared domain representation."""
    return is_shared_effect(value) or isinstance(value, _SPELL_EFFECT_TYPES)


def compile_capability_effect(value: object) -> domain.CapabilityEffect:
    """Compile an authored action or spell effect into the shared model."""
    if is_shared_effect(value):
        return compile_effect(value)
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
            compile_duration(value.duration),
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
            compile_duration(value.duration),
        )
    if isinstance(value, spell_effects.DamageReductionEffectSchema):
        return domain.DamageReductionEffect(
            damage_types=tuple(value.damage_types),
            dice=value.dice,
            selection=value.selection,
            limit=value.limit,
            period=value.period,
            duration=compile_duration(value.duration),
        )
    if isinstance(value, spell_effects.SpeedModifierEffectSchema):
        return domain.SpeedModifierEffect(
            value.feet,
            compile_duration(value.duration),
        )
    if isinstance(value, spell_effects.ConditionSaveAdvantageEffectSchema):
        return domain.ConditionSaveAdvantageEffect(
            tuple(value.conditions),
            compile_duration(value.duration),
        )
    if isinstance(value, spell_effects.DamageImmunityEffectSchema):
        return domain.DamageImmunityEffect(
            tuple(value.damage_types),
            compile_duration(value.duration),
        )
    if isinstance(value, spell_effects.ConditionImmunityEffectSchema):
        return domain.ConditionImmunityEffect(
            tuple(value.conditions),
            value.suppress_existing,
            compile_duration(value.duration),
        )
    if isinstance(value, spell_effects.SenseEffectSchema):
        return domain.SenseEffect(
            value.sense,
            value.range_feet,
            compile_duration(value.duration),
        )
    if isinstance(value, spell_effects.HitPointMaximumModifierEffectSchema):
        return domain.HitPointMaximumModifierEffect(
            value.value,
            value.also_modify_current,
            compile_duration(value.duration),
        )
    raise TypeError(f"Unsupported capability effect: {type(value).__name__}")
