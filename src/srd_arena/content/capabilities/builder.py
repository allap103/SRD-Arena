"""Build domain capabilities from validated authored schemas."""

from dataclasses import replace
from typing import Literal, Protocol, TypeGuard, cast
from collections.abc import Iterable, Sequence

import srd_arena.domain.capabilities as domain

from . import effects, requirements, resolutions, scaling, targets
from .durations import EffectDurationSchema
from .errors import CapabilityBuildError
from .executable import (
    EXECUTABLE_EFFECT_TYPES,
    EXECUTABLE_REQUIREMENT_TYPES,
)


class _SpellRepeatSaveLike(Protocol):
    trigger: str
    ability: str | None
    on_failure: object | None
    successes_required: int
    failures_required: int | None
    counters_need_not_be_consecutive: bool


class _ActionRepeatSaveLike(Protocol):
    trigger: str
    interval_amount: int | None
    interval_unit: Literal["hour", "day"] | None
    distance_from_source_feet: int | None
    effects_end_on_success: bool
    automatic_success_after: EffectDurationSchema | None


class _SaveModifierLike(Protocol):
    roll: str
    mode: str
    ability: str | None
    dice: str | None
    value: int | None
    duration: EffectDurationSchema | None
    requirements: Sequence[object]


class _RepetitionLike(Protocol):
    count: int | Literal["spellcasting_modifier", "slot_scaled"]
    allocation: Literal[
        "same_target", "same_or_different", "different_targets", "propagating"
    ]
    simultaneous: bool
    propagation_range_feet: int | None
    cannot_repeat_target: bool


class _TriggerLike(Protocol):
    event: str
    resolution: object
    requirements: Sequence[object]


class _SequenceStepLike(Protocol):
    target: object | None
    resolution: object


class _SequenceLike(Protocol):
    steps: Sequence[_SequenceStepLike]


def is_shared_effect(value: object) -> TypeGuard[effects.ActionEffectSchema]:
    return isinstance(value, EXECUTABLE_EFFECT_TYPES)


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


def build_capability(
    *,
    target: object,
    resolution: object,
    content: str,
    condition_selection: Literal["all", "choose_one"] = "all",
    scaling_rules: Iterable[scaling.CapabilityScalingSchema] = (),
    triggers: Iterable[object] = (),
    additional_scaling: Iterable[domain.CapabilityScaling] = (),
    location: str = "capability.resolution",
) -> domain.CapabilityDefinition:
    """Build the executable subset of the shared capability vocabulary.

    Source packages may add non-executable authoring schemas, but executable
    targets, resolutions, effects, requirements, repetition, and scaling all
    converge here. Unsupported structured mechanics fail with their authored
    location instead of being silently omitted.
    """
    outer_resolution = _resolution_root(resolution)
    sequence = (
        outer_resolution
        if isinstance(outer_resolution, resolutions.SequenceResolutionSchemaBase)
        else None
    )
    primary_resolution = outer_resolution
    primary_location = location
    if sequence is not None:
        steps = tuple(getattr(sequence, "steps", ()))
        if not steps:
            raise CapabilityBuildError(
                content=content,
                location=f"{location}.steps",
                mechanic="empty sequence",
            )
        primary_resolution = _resolution_root(steps[0].resolution)
        primary_location += ".steps[0].resolution"
    repeated = (
        primary_resolution
        if isinstance(primary_resolution, resolutions.RepeatResolutionSchemaBase)
        else None
    )
    if repeated is not None:
        primary_resolution = _resolution_root(getattr(repeated, "resolution", None))
        primary_location += ".resolution"

    definition = _build_authored_definition(
        target,
        primary_resolution,
        condition_selection=condition_selection,
        content=content,
        location=primary_location,
    )
    return replace(
        definition,
        repetition=_build_repetition(repeated),
        scaling=(
            *_build_scaling_rules(scaling_rules),
            *tuple(additional_scaling),
        ),
        triggers=_build_triggers(target, triggers, content=content),
        follow_ups=_build_follow_ups(
            target,
            sequence,
            content=content,
            location=location,
        ),
    )


def _build_authored_definition(
    target: object,
    resolution: object,
    *,
    condition_selection: Literal["all", "choose_one"],
    content: str,
    location: str,
) -> domain.CapabilityDefinition:
    built_target = _build_authored_target(
        target,
        content=content,
        location="capability.target",
    )
    built_resolution = _build_authored_resolution(
        resolution,
        content=content,
        location=location,
    )
    return build_definition(
        target=built_target,
        resolution=built_resolution,
        condition_selection=condition_selection,
    )


def _build_authored_target(
    value: object,
    *,
    content: str,
    location: str,
) -> domain.CapabilityTarget:
    if isinstance(value, targets.SelfTargetSchema):
        return build_capability_target(kind="self")
    if isinstance(value, targets.CreatureTargetSchema):
        maximum = _normalize_count(value.count.maximum)
        return build_capability_target(
            kind="creature",
            count=domain.TargetCount(value.count.minimum, maximum),
            line_of_sight=value.line_of_sight,
            disposition=value.disposition,
            selection=value.selection,
            requirements=(build_requirement(item) for item in value.requirements),
        )
    if isinstance(value, targets.AreaTargetSchema):
        chosen = value.chosen_count
        geometry = value.geometry
        return build_capability_target(
            kind="area",
            count=(
                domain.TargetCount(chosen.minimum, _normalize_count(chosen.maximum))
                if chosen is not None
                else domain.TargetCount()
            ),
            shape=geometry.shape,
            size_feet=(
                geometry.radius_feet or geometry.length_feet or geometry.diameter_feet
            ),
            width_feet=geometry.width_feet,
            origin=value.origin,
            occupants=value.occupants,
            excludes_source=value.excludes_source,
            requirements=(build_requirement(item) for item in value.requirements),
        )
    if isinstance(
        value,
        (targets.ActionCreatureTargetSchema, targets.ActionAreaTargetSchema),
    ):
        return build_target(value)
    raise CapabilityBuildError(
        content=content,
        location=location,
        mechanic=type(value).__name__,
    )


def _build_authored_resolution(
    value: object,
    *,
    content: str,
    location: str,
) -> domain.CapabilityResolution:
    if isinstance(value, resolutions.FixedAttackResolutionSchema):
        return build_attack_resolution(
            modes=value.attack_modes,
            attack_bonus=domain.FixedAttackBonus(value.attack_bonus),
            hit=domain.Outcome(
                build_effects(value.hit, content=content, location=f"{location}.hit")
            ),
        )
    if isinstance(value, resolutions.AttackResolutionSchema):
        return build_attack_resolution(
            modes=(value.mode,),
            attack_bonus=domain.DerivedAttackBonus("spell_attack_modifier"),
            hit=_build_outcome(
                value.hit,
                content=content,
                location=f"{location}.hit",
            ),
            miss=_build_outcome(
                value.miss,
                content=content,
                location=f"{location}.miss",
            ),
            attacks=value.attacks,
            allocation=value.allocation,
        )
    if isinstance(value, resolutions.AutomaticResolutionSchema):
        return build_automatic_resolution(
            _build_outcome(
                value.outcome,
                content=content,
                location=f"{location}.outcome",
            )
        )
    if isinstance(value, resolutions.SavingThrowResolutionSchema):
        return _build_saving_throw(value, content=content, location=location)
    raise CapabilityBuildError(
        content=content,
        location=location,
        mechanic=type(value).__name__,
    )


def _build_saving_throw(
    value: resolutions.SavingThrowResolutionSchema[object, object],
    *,
    content: str,
    location: str,
) -> domain.SavingThrowResolution:
    if value.ability is None:
        raise CapabilityBuildError(
            content=content,
            location=f"{location}.ability",
            mechanic="saving throw without an ability",
        )
    failure_value = value.failure
    if isinstance(failure_value, list):
        failure = tuple(
            domain.OutcomeStage(
                effects=build_effects(
                    stage.effects,
                    content=content,
                    location=f"{location}.failure[{index}].effects",
                ),
                repeat_saves=tuple(
                    _build_repeat_save(item, value.ability, content, location)
                    for item in getattr(stage, "repeat_saves", ())
                ),
            )
            for index, stage in enumerate(failure_value)
        )
    else:
        outcome = _build_outcome(
            failure_value,
            content=content,
            location=f"{location}.failure",
        )
        repeat = getattr(value, "repeat_save", None)
        failure = (
            domain.OutcomeStage(
                outcome.effects,
                (
                    (_build_repeat_save(repeat, value.ability, content, location),)
                    if repeat is not None
                    else ()
                ),
            ),
        )
    return build_saving_throw_resolution(
        ability=_normalize_ability(value.ability) or value.ability,
        difficulty=_build_difficulty(value.difficulty),
        failure=failure,
        success=_build_optional_outcome(
            value.success,
            content=content,
            location=f"{location}.success",
        ),
        always=_build_optional_outcome(
            getattr(value, "always", None),
            content=content,
            location=f"{location}.always",
        ),
        success_damage=value.success_damage,
        automatic_success=(
            _build_checked_requirement(item, content, f"{location}.automatic_success")
            for item in getattr(value, "automatic_success", ())
        ),
        automatic_failure=(
            _build_checked_requirement(item, content, f"{location}.automatic_failure")
            for item in getattr(value, "automatic_failure", ())
        ),
        save_modifiers=(
            _build_save_modifier(item, content, f"{location}.save_modifiers")
            for item in getattr(value, "save_modifiers", ())
        ),
    )


def _build_outcome(
    value: object,
    *,
    content: str,
    location: str,
) -> domain.Outcome:
    values = tuple(
        getattr(effect, "root", effect) for effect in getattr(value, "effects", ())
    )
    return domain.Outcome(
        build_effects(values, content=content, location=f"{location}.effects"),
        bool(getattr(value, "end_spell", False)),
    )


def _build_optional_outcome(
    value: object | None,
    *,
    content: str,
    location: str,
) -> domain.Outcome:
    if value is None:
        return domain.Outcome()
    return _build_outcome(value, content=content, location=location)


def _build_difficulty(value: object) -> domain.DifficultyClass:
    if isinstance(value, resolutions.FixedDifficultyClassSchema):
        return domain.FixedDifficultyClass(value.value)
    derived = cast(resolutions.DerivedDifficultyClassSchema, value)
    return domain.DerivedDifficultyClass(derived.type)


def _build_repeat_save(
    value: object,
    default_ability: str,
    content: str,
    location: str,
) -> domain.RepeatSave:
    if hasattr(value, "on_failure"):
        spell_repeat = cast(_SpellRepeatSaveLike, value)
        failure_effects: tuple[domain.CapabilityEffect, ...] = ()
        authored_failure = spell_repeat.on_failure
        if authored_failure is not None:
            failure_resolution = _resolution_root(authored_failure)
            if not isinstance(
                failure_resolution,
                resolutions.AutomaticResolutionSchema,
            ):
                raise CapabilityBuildError(
                    content=content,
                    location=f"{location}.repeat_save.on_failure",
                    mechanic=type(failure_resolution).__name__,
                )
            failure_effects = _build_outcome(
                failure_resolution.outcome,
                content=content,
                location=f"{location}.repeat_save.on_failure.outcome",
            ).effects
        trigger_aliases = {"turn_end": "end_of_turn", "turn_start": "start_of_turn"}
        trigger = trigger_aliases.get(spell_repeat.trigger, spell_repeat.trigger)
        return domain.RepeatSave(
            trigger=trigger,
            ability=_normalize_ability(spell_repeat.ability or default_ability),
            failure_effects=failure_effects,
            successes_required=spell_repeat.successes_required,
            failures_required=spell_repeat.failures_required,
            counters_need_not_be_consecutive=(
                spell_repeat.counters_need_not_be_consecutive
            ),
        )
    action_repeat = cast(_ActionRepeatSaveLike, value)
    return domain.RepeatSave(
        trigger=action_repeat.trigger,
        interval_amount=action_repeat.interval_amount,
        interval_unit=action_repeat.interval_unit,
        distance_from_source_feet=action_repeat.distance_from_source_feet,
        effects_end_on_success=action_repeat.effects_end_on_success,
        automatic_success_after=build_duration(action_repeat.automatic_success_after),
    )


def _build_checked_requirement(
    value: object,
    content: str,
    location: str,
) -> domain.CapabilityRequirement:
    if not isinstance(
        value,
        EXECUTABLE_REQUIREMENT_TYPES,
    ):
        raise CapabilityBuildError(
            content=content,
            location=location,
            mechanic=type(value).__name__,
        )
    return build_requirement(value)


def _build_save_modifier(
    value: object,
    content: str,
    location: str,
) -> domain.RollModifierEffect:
    modifier = cast(_SaveModifierLike, value)
    return domain.RollModifierEffect(
        roll=modifier.roll,
        mode=modifier.mode,
        ability=_normalize_ability(modifier.ability),
        dice=modifier.dice,
        value=modifier.value,
        duration=build_duration(modifier.duration),
        requirements=tuple(
            _build_checked_requirement(item, content, location)
            for item in modifier.requirements
        ),
    )


def _build_repetition(value: object | None) -> domain.CapabilityRepetition | None:
    if value is None:
        return None
    repetition = cast(_RepetitionLike, value)
    count = repetition.count
    return domain.CapabilityRepetition(
        count=(
            "ability_modifier"
            if count == "spellcasting_modifier"
            else "resource_scaled"
            if count == "slot_scaled"
            else count
        ),
        allocation=repetition.allocation,
        simultaneous=repetition.simultaneous,
        propagation_range_feet=repetition.propagation_range_feet,
        cannot_repeat_target=repetition.cannot_repeat_target,
    )


def _build_scaling_rules(
    values: Iterable[scaling.CapabilityScalingSchema],
) -> tuple[domain.CapabilityScaling, ...]:
    built: list[domain.CapabilityScaling] = []
    for value in values:
        if isinstance(value, scaling.ResourceScalingSchema):
            built.append(
                domain.CapabilityScaling(
                    basis="resource_level",
                    above_level=(
                        "base_level"
                        if value.above_level == "spell_level"
                        else value.above_level
                    ),
                    per_level=tuple(
                        domain.ScalingIncrement(
                            increment.type,
                            increment.amount,
                            increment.damage_type,
                        )
                        for increment in value.per_level
                    ),
                )
            )
        else:
            built.append(
                domain.CapabilityScaling(
                    basis="actor_level",
                    thresholds=tuple(
                        domain.ScalingThreshold(
                            threshold.minimum_level,
                            (
                                domain.ScalingIncrement(
                                    "projectile_count",
                                    threshold.projectile_count,
                                ),
                            ),
                        )
                        for threshold in value.thresholds
                    ),
                )
            )
    return tuple(built)


def _build_triggers(
    target: object,
    values: Iterable[object],
    *,
    content: str,
) -> tuple[domain.CapabilityTrigger, ...]:
    built: list[domain.CapabilityTrigger] = []
    for index, raw_value in enumerate(values):
        value = cast(_TriggerLike, raw_value)
        location = f"capability.outcome_triggers[{index}].resolution"
        nested = build_capability(
            target=target,
            resolution=value.resolution,
            content=content,
            location=location,
        )
        built.append(
            domain.CapabilityTrigger(
                event=value.event,
                resolution=nested.resolution,
                requirements=tuple(
                    _build_checked_requirement(item, content, location)
                    for item in value.requirements
                ),
            )
        )
    return tuple(built)


def _build_follow_ups(
    target: object,
    sequence: object | None,
    *,
    content: str,
    location: str,
) -> tuple[domain.CapabilityStep, ...]:
    if sequence is None:
        return ()
    authored_sequence = cast(_SequenceLike, sequence)
    built: list[domain.CapabilityStep] = []
    for index, step in enumerate(tuple(authored_sequence.steps)[1:], start=1):
        nested = build_capability(
            target=step.target or target,
            resolution=step.resolution,
            content=content,
            location=f"{location}.steps[{index}].resolution",
        )
        built.append(domain.CapabilityStep(nested.target, nested.resolution))
    return tuple(built)


def _resolution_root(value: object) -> object:
    return getattr(value, "root", value)


def _normalize_count(
    value: int | Literal["spellcasting_modifier", "all"],
) -> int | Literal["ability_modifier", "all"]:
    return "ability_modifier" if value == "spellcasting_modifier" else value


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
