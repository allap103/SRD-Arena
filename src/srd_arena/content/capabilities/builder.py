"""Build domain capability primitives from authored schemas."""

from collections.abc import Iterable
from typing import Literal, TypeGuard, assert_never

import srd_arena.domain.capabilities as domain

from . import durations, effects, requirements, targets
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
    """Return whether an effect belongs to the cross-content capability grammar.

    >>> damage = effects.DamageEffectSchema(
    ...     type="damage", dice="1d6", damage_type="fire")
    >>> is_shared_effect(damage)
    True
    """

    return isinstance(value, _SHARED_EFFECT_TYPES)


def build_target(value: targets.ActionTargetSchema) -> domain.CapabilityTarget:
    """Translate an authored target selector into its domain targeting contract.

    >>> target = build_target(targets.SelfTargetSchema(type="self"))
    >>> (target.kind, target.count.maximum, target.origin)
    ('self', 1, 'self')
    """

    if isinstance(value, targets.SelfTargetSchema):
        return domain.CapabilityTarget(kind="self")
    if isinstance(value, targets.CreatureTargetSchema):
        return domain.CapabilityTarget(
            kind="creature",
            count=domain.TargetCount(maximum=value.count),
            range_feet=value.range_feet,
            line_of_sight=value.line_of_sight,
            requirements=tuple(
                build_requirement(requirement) for requirement in value.requirements
            ),
        )
    if isinstance(value, targets.AreaTargetSchema):
        occupants: Literal["all", "allies", "enemies", "chosen"]
        if value.affects == "allies":
            occupants = "allies"
        elif value.affects == "enemies":
            occupants = "enemies"
        else:
            occupants = "all"
        affected_entities: Literal[
            "creatures",
            "objects",
            "creatures_and_objects",
        ]
        if value.affects == "objects":
            affected_entities = "objects"
        elif value.affects == "all":
            affected_entities = "creatures_and_objects"
        else:
            affected_entities = "creatures"
        return domain.CapabilityTarget(
            kind="area",
            range_feet=value.range_feet,
            shape=value.shape,
            size_feet=value.size_feet,
            width_feet=value.width_feet,
            origin=value.origin,
            occupants=occupants,
            excludes_source=value.excludes_self,
            affected_entities=affected_entities,
            requirements=tuple(
                build_requirement(requirement) for requirement in value.requirements
            ),
        )
    assert_never(value)


def build_requirement(
    value: requirements.ActionRequirementSchema,
) -> domain.CapabilityRequirement:
    """Translate an authored eligibility clause into a domain requirement.

    >>> schema = requirements.CreatureTypeRequirementSchema(
    ...     type="creature_type", creature_types=["humanoid"])
    >>> build_requirement(schema).creature_types
    ('humanoid',)
    """

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
    if isinstance(value, requirements.NotAffectedRequirementSchema):
        return domain.NotAffectedRequirement(value.action)
    assert_never(value)


def build_duration(
    value: EffectDurationSchema | None,
) -> domain.EffectDuration | None:
    """Translate authored timing and ending fields into an effect duration.

    >>> from .durations import TimedDurationSchema
    >>> duration = build_duration(
    ...     TimedDurationSchema(type="timed", amount=1, unit="minute"))
    >>> (duration.kind, duration.amount, duration.unit)
    ('timed', 1, 'minute')
    >>> build_duration(None) is None
    True
    """

    if value is None:
        return None
    if isinstance(value, durations.EndOfTurnDurationSchema):
        return domain.EffectDuration(
            kind="end_of_turn",
            creature=value.creature,
            turn_offset=value.turn_offset,
        )
    if isinstance(value, durations.StartOfTurnDurationSchema):
        return domain.EffectDuration(
            kind="start_of_turn",
            creature=value.creature,
            turn_offset=value.turn_offset,
        )
    if isinstance(value, durations.TimedDurationSchema):
        return domain.EffectDuration(
            kind="timed",
            amount=value.amount,
            unit=value.unit,
        )
    if isinstance(value, durations.UntilEventDurationSchema):
        return domain.EffectDuration(
            kind="until_event",
            events=tuple(value.events),
            event_match=value.match,
        )
    if isinstance(value, durations.PermanentDurationSchema):
        return domain.EffectDuration(kind="permanent")
    assert_never(value)


def build_effect(value: effects.ActionEffectSchema) -> domain.CapabilityEffect:
    """Translate one declarative effect while preserving source-relative semantics.

    >>> schema = effects.DamageEffectSchema(
    ...     type="damage", dice="1d6", damage_type="fire")
    >>> effect = build_effect(schema)
    >>> (effect.dice, effect.damage_type)
    ('1d6', 'fire')
    """

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
    memories = value
    return domain.GainMemoriesEffect(
        domain.CreatureTypeRequirement(tuple(memories.requirement.creature_types)),
        memories.trigger,
    )


def build_outcome(
    values: Iterable[effects.ActionEffectSchema],
) -> domain.Outcome:
    """Translate an ordered authored outcome into domain resolution effects.

    >>> damage = effects.DamageEffectSchema(
    ...     type="damage", dice="1d6", damage_type="cold")
    >>> [type(effect).__name__ for effect in build_outcome([damage]).effects]
    ['DamageEffect']
    """

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
