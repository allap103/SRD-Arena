"""Build domain effects from authored effect schemas."""

from collections.abc import Iterable
from typing import TypeGuard, cast

import srd_arena.domain.capabilities as domain

from srd_arena.content.capabilities.schemas import effects
from srd_arena.content.capabilities.schemas.durations import EffectDurationSchema
from .common import build_duration, normalize_ability
from .errors import CapabilityBuildError
from .requirements import build_requirement
from .supported import EXECUTABLE_EFFECT_TYPES


def is_executable_effect(value: object) -> TypeGuard[effects.ActionEffectSchema]:
    return isinstance(value, EXECUTABLE_EFFECT_TYPES)


def build_effect(value: effects.ActionEffectSchema) -> domain.CapabilityEffect:
    if isinstance(value, effects.DamageEffectSchema):
        return domain.DamageEffect(
            dice=value.dice,
            bonus=value.bonus,
            damage_type=value.damage_type,
            minimum=value.minimum,
            requirements=tuple(
                domain.AttackRollModeRequirement(requirement.mode)
                for requirement in value.requirements
            ),
            modifier=value.modifier,
        )
    if isinstance(value, effects.HealingEffectSchema):
        return domain.HealingEffect(
            dice=value.dice,
            bonus=value.bonus,
            modifier=("none" if value.modifier == "none" else "ability_modifier"),
            from_damage=value.from_damage,
            restore_to_maximum=value.restore_to_maximum,
            pool=value.pool,
        )
    if isinstance(value, effects.TemporaryHitPointsEffectSchema):
        return domain.TemporaryHitPointsEffect(
            dice=value.dice,
            value=value.value,
            modifier=("none" if value.modifier == "none" else "ability_modifier"),
            trigger=value.trigger,
        )
    if isinstance(value, effects.ArmorClassModifierEffectSchema):
        return domain.ArmorClassModifierEffect(
            value.value,
            build_duration(value.duration),
        )
    if isinstance(value, effects.RemoveEffectSchema):
        return domain.RemoveEffect(
            removable=tuple(value.removable),
            selection=value.selection,
            conditions=tuple(value.conditions),
        )
    if isinstance(value, effects.DamageResistanceEffectSchema):
        return domain.DamageResistanceEffect(
            tuple(value.damage_types),
            value.selection,
            build_duration(value.duration),
        )
    if isinstance(value, effects.DamageReductionEffectSchema):
        return domain.DamageReductionEffect(
            damage_types=tuple(value.damage_types),
            dice=value.dice,
            selection=value.selection,
            limit=value.limit,
            period=value.period,
            duration=build_duration(value.duration),
        )
    if isinstance(value, effects.SpeedModifierEffectSchema):
        return domain.SpeedModifierEffect(
            value.feet,
            build_duration(value.duration),
        )
    if isinstance(value, effects.ConditionSaveAdvantageEffectSchema):
        return domain.ConditionSaveAdvantageEffect(
            tuple(value.conditions),
            build_duration(value.duration),
        )
    if isinstance(value, effects.DamageImmunityEffectSchema):
        return domain.DamageImmunityEffect(
            tuple(value.damage_types),
            build_duration(value.duration),
        )
    if isinstance(value, effects.ConditionImmunityEffectSchema):
        return domain.ConditionImmunityEffect(
            tuple(value.conditions),
            value.suppress_existing,
            build_duration(value.duration),
        )
    if isinstance(value, effects.SenseEffectSchema):
        return domain.SenseEffect(
            value.sense,
            value.range_feet,
            build_duration(value.duration),
        )
    if isinstance(value, effects.HitPointMaximumModifierEffectSchema):
        return domain.HitPointMaximumModifierEffect(
            value.value,
            value.also_modify_current,
            build_duration(value.duration),
        )
    if isinstance(value, effects.ConditionEffectSchema):
        return domain.ConditionEffect(
            condition=value.condition,
            duration=build_duration(value.duration),
            requirements=tuple(
                build_requirement(requirement) for requirement in value.requirements
            ),
            escape_dc=value.escape_dc,
            source_capacity=value.source_capacity,
            ends_on=tuple(value.ends_on),
        )
    if isinstance(value, effects.ForcedMovementEffectSchema):
        return domain.ForcedMovementEffect(
            value.direction,
            value.distance_feet,
            value.up_to,
        )
    if isinstance(value, effects.SpeedMultiplierEffectSchema):
        return domain.SpeedMultiplierEffect(
            value.numerator,
            value.denominator,
            _required_duration(value.duration),
        )
    if isinstance(value, effects.ProhibitReactionEffectSchema):
        return domain.ProhibitReactionsEffect(_required_duration(value.duration))
    if isinstance(value, effects.TurnEconomyRestrictionEffectSchema):
        return domain.TurnEconomyRestrictionEffect(
            tuple(value.choose_between),
            _required_duration(value.duration),
        )
    if isinstance(value, effects.RollModifierEffectSchema):
        return domain.RollModifierEffect(
            roll=value.roll,
            mode=value.mode,
            ability=normalize_ability(value.ability),
            dice=value.dice,
            value=value.value,
            duration=build_duration(value.duration),
            ability_options=tuple(
                normalize_ability(ability) or ability
                for ability in value.ability_options
            ),
            subject=value.subject,
            ignored_by_senses=tuple(value.ignored_by_senses),
            requirements=tuple(
                build_requirement(requirement) for requirement in value.requirements
            ),
        )
    if isinstance(value, effects.ControlEffectSchema):
        return domain.ControlEffect(
            value.communication,
            value.communication_range_feet,
            value.control_range_feet,
            _required_duration(value.duration),
        )
    memories = cast(effects.GainMemoriesEffectSchema, value)
    return domain.GainMemoriesEffect(
        domain.CreatureTypeRequirement(tuple(memories.requirement.creature_types)),
        memories.trigger,
    )


def build_effects(
    values: Iterable[object],
    *,
    content: str,
    location: str,
) -> tuple[domain.CapabilityEffect, ...]:
    """Build an effect sequence and report unsupported mechanics at their source."""
    built: list[domain.CapabilityEffect] = []
    for index, value in enumerate(values):
        if not is_executable_effect(value):
            raise CapabilityBuildError(
                content=content,
                location=f"{location}[{index}]",
                mechanic=type(value).__name__,
            )
        built.append(build_effect(value))
    return tuple(built)


def _required_duration(value: EffectDurationSchema) -> domain.EffectDuration:
    duration = build_duration(value)
    if duration is None:
        raise ValueError("This effect requires a duration.")
    return duration
