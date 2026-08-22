"""Build domain capability primitives from authored schemas."""

from typing import Literal, TypeGuard, cast
from collections.abc import Iterable

import srd_arena.domain.capabilities as domain

from . import effects, requirements, targets
from .durations import EffectDurationSchema

_SHARED_EFFECT_TYPES = (
    effects.DamageEffectSchema,
    effects.ConditionEffectSchema,
    effects.ForcedMovementEffectSchema,
    effects.SpeedMultiplierEffectSchema,
    effects.ProhibitReactionEffectSchema,
    effects.TurnEconomyRestrictionEffectSchema,
    effects.RollModifierEffectSchema,
    effects.ControlEffectSchema,
    effects.GainMemoriesEffectSchema,
)


def is_shared_effect(value: object) -> TypeGuard[effects.ActionEffectSchema]:
    return isinstance(value, _SHARED_EFFECT_TYPES)


def build_target(value: targets.ActionTargetSchema) -> domain.CapabilityTarget:
    count = getattr(value, "count", 1)
    affects = getattr(value, "affects", "creatures")
    return domain.CapabilityTarget(
        kind=value.type,
        count=domain.TargetCount(maximum=count),
        range_feet=getattr(value, "range_feet", None),
        shape=getattr(value, "shape", None),
        size_feet=getattr(value, "size_feet", None),
        width_feet=getattr(value, "width_feet", None),
        origin=getattr(value, "origin", "self"),
        line_of_sight=getattr(value, "line_of_sight", False),
        occupants=cast(
            Literal["all", "allies", "enemies", "chosen"],
            affects if affects in {"allies", "enemies"} else "all",
        ),
        excludes_source=getattr(value, "excludes_self", False),
        requirements=tuple(
            build_requirement(requirement)
            for requirement in getattr(value, "requirements", ())
        ),
    )


def build_requirement(
    value: requirements.ActionRequirementSchema,
) -> domain.CapabilityRequirement:
    if isinstance(value, requirements.SizeRequirementSchema):
        return domain.SizeRequirement(value.maximum, value.minimum)
    if isinstance(value, requirements.ConditionRequirementSchema):
        return domain.ConditionRequirement(
            tuple(value.conditions),
            value.match,
            value.applied_by,
        )
    if isinstance(value, requirements.CreatureTypeRequirementSchema):
        return domain.CreatureTypeRequirement(tuple(value.creature_types))
    return domain.NotAffectedRequirement(value.action)


def build_duration(
    value: EffectDurationSchema | None,
) -> domain.EffectDuration | None:
    if value is None:
        return None
    return domain.EffectDuration(
        kind=value.type,
        amount=getattr(value, "amount", None),
        unit=getattr(value, "unit", None),
        creature=getattr(value, "creature", None),
        turn_offset=getattr(value, "turn_offset", 0),
        events=tuple(getattr(value, "events", ())),
    )


def build_effect(value: effects.ActionEffectSchema) -> domain.CapabilityEffect:
    if isinstance(value, effects.DamageEffectSchema):
        return domain.DamageEffect(
            value.dice,
            value.bonus,
            value.damage_type,
            value.minimum,
            tuple(
                domain.AttackRollModeRequirement(requirement.mode)
                for requirement in value.requirements
            ),
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
            ability=_normalize_ability(value.ability),
            dice=value.dice,
            value=value.value,
            duration=build_duration(value.duration),
            ability_options=tuple(
                _normalize_ability(ability) or ability
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


def build_outcome(
    values: Iterable[effects.ActionEffectSchema],
) -> domain.Outcome:
    return domain.Outcome(tuple(build_effect(value) for value in values))


def _required_duration(value: EffectDurationSchema) -> domain.EffectDuration:
    duration = build_duration(value)
    if duration is None:
        raise ValueError("This effect requires a duration.")
    return duration


def _normalize_ability(value: str | None) -> str | None:
    if value is None:
        return None
    return {
        "str": "strength",
        "dex": "dexterity",
        "con": "constitution",
        "int": "intelligence",
        "wis": "wisdom",
        "cha": "charisma",
    }.get(value, value)
