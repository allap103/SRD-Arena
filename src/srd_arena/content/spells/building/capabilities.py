from collections.abc import Iterable
from dataclasses import replace
from typing import Literal

import srd_arena.domain.capabilities as domain
from srd_arena.content.capabilities import (
    CapabilityBuildError,
    ConditionRequirementSchema,
    CreatureTypeRequirementSchema,
    FixedDifficultyClassSchema,
    NotAffectedRequirementSchema,
    SizeRequirementSchema,
)
from srd_arena.content.capabilities.builder import (
    build_duration,
    build_requirement,
)
from srd_arena.content.spells.resolution import (
    AutomaticResolutionSchema,
    OutcomeSchema,
    RepeatResolutionSchema,
    RepeatSaveProgressionSchema,
    SavingThrowResolutionSchema,
    SequenceResolutionSchema,
    SpellAttackResolutionSchema,
)
from srd_arena.content.spells.schema import SpellSchema
from srd_arena.content.spells.targeting import (
    AreaSpellTargetSchema,
    ConditionImmunityRequirementSchema,
    CreatureSpellTargetSchema,
    CreatureTraitRequirementSchema,
    RelationshipRequirementSchema,
    SpellSaveModifierSchema,
    SpellTargetSchema,
)

from .effects import build_capability_effect, is_buildable_effect
from .scaling import build_scaling
from .targeting import normalize_save_ability

SpellResolutionSchema = (
    AutomaticResolutionSchema
    | SavingThrowResolutionSchema
    | SpellAttackResolutionSchema
)


def build_spell_definition(
    raw: SpellSchema,
) -> domain.CapabilityDefinition | None:
    """Build an executable spell, rejecting unsupported structured mechanics."""
    if not raw.executable:
        return None
    assert raw.capability is not None
    content = f"Spell '{raw.public_name}'"
    resolution: object = raw.capability.resolution.root
    resolution_location = "capability.resolution"
    if isinstance(resolution, SequenceResolutionSchema):
        resolution = resolution.steps[0].resolution.root
        resolution_location += ".steps[0].resolution"
    repeated = resolution if isinstance(resolution, RepeatResolutionSchema) else None
    if repeated is not None:
        resolution = repeated.resolution.root
        resolution_location += ".resolution"
    if not isinstance(
        resolution,
        (
            AutomaticResolutionSchema,
            SavingThrowResolutionSchema,
            SpellAttackResolutionSchema,
        ),
    ):
        raise CapabilityBuildError(
            content=content,
            location=resolution_location,
            mechanic=type(resolution).__name__,
        )
    outcome = (
        resolution.failure
        if isinstance(resolution, SavingThrowResolutionSchema)
        else resolution.hit
        if isinstance(resolution, SpellAttackResolutionSchema)
        else resolution.outcome
    )
    definition = build_definition(
        raw.capability.target,
        resolution,
        outcome,
        raw.capability.condition_application,
        content=content,
        location=resolution_location,
    )
    repetition = (
        domain.CapabilityRepetition(
            count=(
                "ability_modifier"
                if repeated.count == "spellcasting_modifier"
                else "resource_scaled"
                if repeated.count == "slot_scaled"
                else repeated.count
            ),
            allocation=repeated.allocation,
            simultaneous=repeated.simultaneous,
            propagation_range_feet=repeated.propagation_range_feet,
            cannot_repeat_target=repeated.cannot_repeat_target,
        )
        if repeated is not None
        else None
    )
    return replace(
        definition,
        repetition=repetition,
        scaling=build_scaling(raw),
        triggers=_build_triggers(raw),
        follow_ups=_build_follow_ups(raw),
    )


def build_definition(
    target: SpellTargetSchema,
    resolution: SpellResolutionSchema,
    outcome: OutcomeSchema,
    condition_selection: Literal["all", "choose_one"] = "all",
    *,
    content: str = "Spell capability",
    location: str = "capability.resolution",
) -> domain.CapabilityDefinition:
    effect_values = tuple(effect.root for effect in outcome.effects)
    success_values = (
        tuple(effect.root for effect in resolution.success.effects)
        if isinstance(resolution, SavingThrowResolutionSchema)
        else ()
    )
    miss_values = (
        tuple(effect.root for effect in resolution.miss.effects)
        if isinstance(resolution, SpellAttackResolutionSchema)
        else ()
    )
    outcome_name = (
        "failure"
        if isinstance(resolution, SavingThrowResolutionSchema)
        else "hit"
        if isinstance(resolution, SpellAttackResolutionSchema)
        else "outcome"
    )
    built_effects = _build_effects(
        effect_values,
        content=content,
        location=f"{location}.{outcome_name}.effects",
    )
    built_success = _build_effects(
        success_values,
        content=content,
        location=f"{location}.success.effects",
    )
    built_miss = _build_effects(
        miss_values,
        content=content,
        location=f"{location}.miss.effects",
    )
    built_target = _build_target(
        target,
        content=content,
        location="capability.target",
    )
    built_outcome = domain.Outcome(
        built_effects,
        outcome.end_spell,
    )
    built_resolution = _build_resolution(
        resolution,
        built_outcome,
        built_success,
        built_miss,
        (
            resolution.success.end_spell
            if isinstance(resolution, SavingThrowResolutionSchema)
            else False
        ),
        (
            resolution.miss.end_spell
            if isinstance(resolution, SpellAttackResolutionSchema)
            else False
        ),
        content=content,
        location=location,
    )
    return domain.CapabilityDefinition(
        built_target,
        built_resolution,
        condition_selection=condition_selection,
    )


def _build_resolution(
    resolution: SpellResolutionSchema,
    outcome: domain.Outcome,
    success_effects: tuple[domain.CapabilityEffect, ...],
    miss_effects: tuple[domain.CapabilityEffect, ...],
    success_ends_capability: bool,
    miss_ends_capability: bool,
    *,
    content: str,
    location: str,
) -> domain.CapabilityResolution:
    if isinstance(resolution, SpellAttackResolutionSchema):
        return domain.AttackResolution(
            modes=(resolution.mode,),
            attack_bonus=domain.DerivedAttackBonus("spell_attack_modifier"),
            hit=outcome,
            miss=domain.Outcome(miss_effects, miss_ends_capability),
            attacks=resolution.attacks,
            allocation=resolution.allocation,
        )
    if isinstance(resolution, AutomaticResolutionSchema):
        return domain.AutomaticResolution(outcome)
    if resolution.ability is None:
        raise CapabilityBuildError(
            content=content,
            location=f"{location}.ability",
            mechanic="saving throw without an ability",
        )
    difficulty = resolution.difficulty
    if isinstance(difficulty, FixedDifficultyClassSchema):
        built_difficulty: domain.DifficultyClass = domain.FixedDifficultyClass(
            difficulty.value
        )
    else:
        built_difficulty = domain.DerivedDifficultyClass(difficulty.type)
    return domain.SavingThrowResolution(
        ability=normalize_save_ability(resolution.ability),
        difficulty=built_difficulty,
        failure=(
            domain.OutcomeStage(
                outcome.effects,
                (
                    _build_repeat_save(
                        resolution.repeat_save,
                        resolution.ability,
                        content=content,
                        location=f"{location}.repeat_save",
                    ),
                )
                if resolution.repeat_save is not None
                else (),
            ),
        ),
        success=domain.Outcome(
            success_effects,
            success_ends_capability,
        ),
        success_damage=resolution.success_damage,
        automatic_success=tuple(
            _build_spell_requirement(requirement)
            for requirement in resolution.automatic_success
        ),
        automatic_failure=tuple(
            _build_spell_requirement(requirement)
            for requirement in resolution.automatic_failure
        ),
        save_modifiers=tuple(
            _build_save_modifier(modifier) for modifier in resolution.save_modifiers
        ),
    )


def _build_triggers(raw: SpellSchema) -> tuple[domain.CapabilityTrigger, ...]:
    assert raw.capability is not None
    built: list[domain.CapabilityTrigger] = []
    content = f"Spell '{raw.public_name}'"
    for index, trigger in enumerate(raw.capability.outcome_triggers):
        location = f"capability.outcome_triggers[{index}].resolution"
        resolution = trigger.resolution.root
        if not isinstance(
            resolution,
            (
                AutomaticResolutionSchema,
                SavingThrowResolutionSchema,
                SpellAttackResolutionSchema,
            ),
        ):
            raise CapabilityBuildError(
                content=content,
                location=location,
                mechanic=type(resolution).__name__,
            )
        outcome = (
            resolution.failure
            if isinstance(resolution, SavingThrowResolutionSchema)
            else resolution.hit
            if isinstance(resolution, SpellAttackResolutionSchema)
            else resolution.outcome
        )
        nested = build_definition(
            raw.capability.target,
            resolution,
            outcome,
            content=content,
            location=location,
        )
        built.append(
            domain.CapabilityTrigger(
                event=trigger.event,
                resolution=nested.resolution,
                requirements=tuple(
                    _build_spell_requirement(requirement)
                    for requirement in trigger.requirements
                ),
            )
        )
    return tuple(built)


def _build_follow_ups(raw: SpellSchema) -> tuple[domain.CapabilityStep, ...]:
    assert raw.capability is not None
    outer = raw.capability.resolution.root
    if not isinstance(outer, SequenceResolutionSchema):
        return ()
    built: list[domain.CapabilityStep] = []
    content = f"Spell '{raw.public_name}'"
    for index, step in enumerate(outer.steps[1:], start=1):
        location = f"capability.resolution.steps[{index}].resolution"
        resolution = step.resolution.root
        if not isinstance(
            resolution,
            (
                AutomaticResolutionSchema,
                SavingThrowResolutionSchema,
                SpellAttackResolutionSchema,
            ),
        ):
            raise CapabilityBuildError(
                content=content,
                location=location,
                mechanic=type(resolution).__name__,
            )
        outcome = (
            resolution.failure
            if isinstance(resolution, SavingThrowResolutionSchema)
            else resolution.hit
            if isinstance(resolution, SpellAttackResolutionSchema)
            else resolution.outcome
        )
        nested = build_definition(
            step.target or raw.capability.target,
            resolution,
            outcome,
            content=content,
            location=location,
        )
        built.append(domain.CapabilityStep(nested.target, nested.resolution))
    return tuple(built)


def _build_repeat_save(
    repeat: RepeatSaveProgressionSchema,
    default_ability: str,
    *,
    content: str,
    location: str,
) -> domain.RepeatSave:
    failure_effects: tuple[domain.CapabilityEffect, ...] = ()
    if repeat.on_failure is not None:
        failure = repeat.on_failure.root
        if not isinstance(failure, AutomaticResolutionSchema):
            raise CapabilityBuildError(
                content=content,
                location=f"{location}.on_failure",
                mechanic=type(failure).__name__,
            )
        failure_effects = _build_effects(
            (effect.root for effect in failure.outcome.effects),
            content=content,
            location=f"{location}.on_failure.outcome.effects",
        )
    trigger_aliases = {
        "turn_end": "end_of_turn",
        "turn_start": "start_of_turn",
    }
    return domain.RepeatSave(
        trigger=trigger_aliases.get(repeat.trigger, repeat.trigger),
        ability=normalize_save_ability(repeat.ability or default_ability),
        failure_effects=failure_effects,
        successes_required=repeat.successes_required,
        failures_required=repeat.failures_required,
        counters_need_not_be_consecutive=repeat.counters_need_not_be_consecutive,
    )


def _build_effects(
    values: Iterable[object],
    *,
    content: str,
    location: str,
) -> tuple[domain.CapabilityEffect, ...]:
    built: list[domain.CapabilityEffect] = []
    for index, effect in enumerate(values):
        if not is_buildable_effect(effect):
            raise CapabilityBuildError(
                content=content,
                location=f"{location}[{index}]",
                mechanic=type(effect).__name__,
            )
        built.append(build_capability_effect(effect))
    return tuple(built)


def _build_spell_requirement(value: object) -> domain.CapabilityRequirement:
    if isinstance(
        value,
        (
            ConditionRequirementSchema,
            CreatureTypeRequirementSchema,
            NotAffectedRequirementSchema,
            SizeRequirementSchema,
        ),
    ):
        return build_requirement(value)
    if isinstance(value, CreatureTraitRequirementSchema):
        return domain.CreatureTraitRequirement(value.trait)
    if isinstance(value, ConditionImmunityRequirementSchema):
        return domain.ConditionImmunityRequirement(value.condition)
    if isinstance(value, RelationshipRequirementSchema):
        return domain.RelationshipRequirement(
            value.relationship,
            value.established_by,
        )
    raise TypeError(f"Unsupported save requirement: {type(value).__name__}")


def _build_save_modifier(
    value: SpellSaveModifierSchema,
) -> domain.RollModifierEffect:
    return domain.RollModifierEffect(
        roll=value.roll,
        mode=value.mode,
        ability=(
            normalize_save_ability(value.ability) if value.ability is not None else None
        ),
        dice=value.dice,
        value=value.value,
        duration=build_duration(value.duration),
        requirements=tuple(
            _build_spell_requirement(requirement) for requirement in value.requirements
        ),
    )


def _build_target(
    target: SpellTargetSchema,
    *,
    content: str,
    location: str,
) -> domain.CapabilityTarget:
    if target.type == "self":
        return domain.CapabilityTarget(kind="self")
    if isinstance(target, CreatureSpellTargetSchema):
        maximum = (
            "ability_modifier"
            if target.count.maximum == "spellcasting_modifier"
            else target.count.maximum
        )
        return domain.CapabilityTarget(
            kind="creature",
            count=domain.TargetCount(target.count.minimum, maximum),
            line_of_sight=target.line_of_sight,
            disposition=target.disposition,
            selection=target.selection,
        )
    if not isinstance(target, AreaSpellTargetSchema):
        raise CapabilityBuildError(
            content=content,
            location=location,
            mechanic=type(target).__name__,
        )
    geometry = target.geometry
    chosen_count = target.chosen_count
    return domain.CapabilityTarget(
        kind="area",
        count=(
            domain.TargetCount(
                chosen_count.minimum,
                (
                    "ability_modifier"
                    if chosen_count.maximum == "spellcasting_modifier"
                    else chosen_count.maximum
                ),
            )
            if chosen_count is not None
            else domain.TargetCount()
        ),
        shape=geometry.shape,
        size_feet=(
            geometry.radius_feet or geometry.length_feet or geometry.diameter_feet
        ),
        width_feet=geometry.width_feet,
        origin=target.origin,
        occupants=target.occupants,
        excludes_source=target.excludes_source,
    )
