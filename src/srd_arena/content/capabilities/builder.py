"""Build domain capability primitives from authored schemas."""

from typing import Literal, TypeGuard, cast
from collections.abc import Iterable

import srd_arena.domain.capabilities as domain

from . import effects, requirements, targets
from .durations import EffectDurationSchema
from .errors import CapabilityBuildError

_SHARED_EFFECT_TYPES = (
    effects.DamageEffectSchema,
    effects.HealingEffectSchema,
    effects.TemporaryHitPointsEffectSchema,
    effects.ArmorClassModifierEffectSchema,
    effects.RemoveEffectSchema,
    effects.DamageResistanceEffectSchema,
    effects.DamageReductionEffectSchema,
    effects.SpeedModifierEffectSchema,
    effects.ConditionSaveAdvantageEffectSchema,
    effects.DamageImmunityEffectSchema,
    effects.ConditionImmunityEffectSchema,
    effects.SenseEffectSchema,
    effects.HitPointMaximumModifierEffectSchema,
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
    return build_capability_target(
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


def build_capability_target(
    *,
    kind: Literal["self", "creature", "area"],
    count: domain.TargetCount = domain.TargetCount(),
    range_feet: int | None = None,
    shape: str | None = None,
    size_feet: int | None = None,
    width_feet: int | None = None,
    origin: str = "self",
    line_of_sight: bool = False,
    disposition: Literal[
        "any", "ally", "enemy", "willing", "source", "trigger_target"
    ] = "any",
    selection: Literal["all", "choose", "choose_up_to"] = "choose",
    occupants: Literal["all", "allies", "enemies", "chosen"] = "all",
    excludes_source: bool = False,
    requirements: Iterable[domain.CapabilityRequirement] = (),
) -> domain.CapabilityTarget:
    """Build the shared target model from a source-specific target adapter."""
    return domain.CapabilityTarget(
        kind=kind,
        count=count,
        range_feet=range_feet,
        shape=shape,
        size_feet=size_feet,
        width_feet=width_feet,
        origin=origin,
        line_of_sight=line_of_sight,
        disposition=disposition,
        selection=selection,
        occupants=occupants,
        excludes_source=excludes_source,
        requirements=tuple(requirements),
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
    if isinstance(value, requirements.NotAffectedRequirementSchema):
        return domain.NotAffectedRequirement(value.action)
    if isinstance(value, requirements.CreatureTraitRequirementSchema):
        return domain.CreatureTraitRequirement(value.trait)
    if isinstance(value, requirements.ConditionImmunityRequirementSchema):
        return domain.ConditionImmunityRequirement(value.condition)
    relationship = cast(requirements.RelationshipRequirementSchema, value)
    return domain.RelationshipRequirement(
        relationship.relationship,
        relationship.established_by,
    )


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


def build_effects(
    values: Iterable[object],
    *,
    content: str,
    location: str,
) -> tuple[domain.CapabilityEffect, ...]:
    """Build an effect sequence and report unsupported mechanics at their source."""
    built: list[domain.CapabilityEffect] = []
    for index, value in enumerate(values):
        if not is_shared_effect(value):
            raise CapabilityBuildError(
                content=content,
                location=f"{location}[{index}]",
                mechanic=type(value).__name__,
            )
        built.append(build_effect(value))
    return tuple(built)


def build_automatic_resolution(
    outcome: domain.Outcome,
) -> domain.AutomaticResolution:
    """Build a resolution whose outcome applies without a roll."""
    return domain.AutomaticResolution(outcome)


def build_attack_resolution(
    *,
    modes: Iterable[Literal["melee", "ranged"]],
    attack_bonus: domain.AttackBonus,
    hit: domain.Outcome,
    miss: domain.Outcome = domain.Outcome(),
    attacks: int = 1,
    allocation: Literal["same_target", "same_or_different"] = "same_target",
) -> domain.AttackResolution:
    """Build the shared attack-resolution model used by any capability source."""
    return domain.AttackResolution(
        modes=tuple(modes),
        attack_bonus=attack_bonus,
        hit=hit,
        miss=miss,
        attacks=attacks,
        allocation=allocation,
    )


def build_saving_throw_resolution(
    *,
    ability: str,
    difficulty: domain.DifficultyClass,
    failure: Iterable[domain.OutcomeStage],
    success: domain.Outcome = domain.Outcome(),
    always: domain.Outcome = domain.Outcome(),
    success_damage: Literal["none", "half"] = "none",
    automatic_success: Iterable[domain.CapabilityRequirement] = (),
    automatic_failure: Iterable[domain.CapabilityRequirement] = (),
    save_modifiers: Iterable[domain.RollModifierEffect] = (),
) -> domain.SavingThrowResolution:
    """Build the shared saving-throw model used by any capability source."""
    return domain.SavingThrowResolution(
        ability=ability,
        difficulty=difficulty,
        failure=tuple(failure),
        success=success,
        always=always,
        success_damage=success_damage,
        automatic_success=tuple(automatic_success),
        automatic_failure=tuple(automatic_failure),
        save_modifiers=tuple(save_modifiers),
    )


def build_definition(
    *,
    target: domain.CapabilityTarget,
    resolution: domain.CapabilityResolution,
    condition_selection: Literal["all", "choose_one"] = "all",
) -> domain.CapabilityDefinition:
    """Combine shared target and resolution models into a capability definition."""
    return domain.CapabilityDefinition(
        target=target,
        resolution=resolution,
        condition_selection=condition_selection,
    )


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
