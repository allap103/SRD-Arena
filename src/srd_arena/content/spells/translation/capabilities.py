from dataclasses import replace
from typing import Literal, cast

from srd_arena.content.capabilities import (
    ConditionRequirementSchema,
    CreatureTypeRequirementSchema,
    DerivedDifficultyClassSchema,
    FixedDifficultyClassSchema,
    NotAffectedRequirementSchema,
    SizeRequirementSchema,
)
from srd_arena.content.capabilities.compiler import (
    compile_duration,
    compile_requirement,
)
import srd_arena.domain.capabilities as domain

from srd_arena.content.spells.resolution import (
    AutomaticResolutionSchema,
    OutcomeSchema,
    RepeatSaveProgressionSchema,
    RepeatResolutionSchema,
    SavingThrowResolutionSchema,
    SequenceResolutionSchema,
    SpellAttackResolutionSchema,
)
from srd_arena.content.spells.schema import SpellSchema
from srd_arena.content.spells.targeting import SpellTargetSchema
from srd_arena.content.spells.targeting import (
    AreaSpellTargetSchema,
    ConditionImmunityRequirementSchema,
    CreatureTraitRequirementSchema,
    CreatureSpellTargetSchema,
    RelationshipRequirementSchema,
    SpellSaveModifierSchema,
)

from .scaling import compile_scaling
from .effects import compile_capability_effect, is_compilable_effect
from .targeting import normalize_save_ability

SpellResolutionSchema = (
    AutomaticResolutionSchema
    | SavingThrowResolutionSchema
    | SpellAttackResolutionSchema
)


def compile_spell_definition(
    raw: SpellSchema,
) -> domain.CapabilityDefinition | None:
    """Compile the primary executable resolution of an authored spell."""
    if raw.capability is None:
        return None
    resolution: object = raw.capability.resolution.root
    if isinstance(resolution, SequenceResolutionSchema):
        resolution = resolution.steps[0].resolution.root
    repeated = resolution if isinstance(resolution, RepeatResolutionSchema) else None
    if repeated is not None:
        resolution = repeated.resolution.root
    if not isinstance(
        resolution,
        (
            AutomaticResolutionSchema,
            SavingThrowResolutionSchema,
            SpellAttackResolutionSchema,
        ),
    ):
        return None
    outcome = (
        resolution.failure
        if isinstance(resolution, SavingThrowResolutionSchema)
        else resolution.hit
        if isinstance(resolution, SpellAttackResolutionSchema)
        else resolution.outcome
    )
    definition = compile_definition(
        raw.capability.target,
        resolution,
        outcome,
        raw.capability.condition_application,
    )
    if definition is None:
        return None
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
        scaling=compile_scaling(raw),
        triggers=_compile_triggers(raw),
        follow_ups=_compile_follow_ups(raw),
    )


def compile_definition(
    target: SpellTargetSchema,
    resolution: SpellResolutionSchema,
    outcome: OutcomeSchema,
    condition_selection: Literal["all", "choose_one"] = "all",
) -> domain.CapabilityDefinition | None:
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
    if not all(
        is_compilable_effect(effect)
        for effect in (*effect_values, *success_values, *miss_values)
    ):
        return None
    compiled_target = _compile_target(target)
    if compiled_target is None:
        return None
    compiled_outcome = domain.Outcome(
        tuple(
            compile_capability_effect(effect)
            for effect in effect_values
            if is_compilable_effect(effect)
        ),
        outcome.end_spell,
    )
    compiled_resolution = _compile_resolution(
        resolution,
        compiled_outcome,
        success_values,
        miss_values,
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
    )
    if compiled_resolution is None:
        return None
    return domain.CapabilityDefinition(
        compiled_target,
        compiled_resolution,
        condition_selection=condition_selection,
    )


def _compile_resolution(
    resolution: SpellResolutionSchema,
    outcome: domain.Outcome,
    success_values: tuple[object, ...],
    miss_values: tuple[object, ...],
    success_ends_capability: bool,
    miss_ends_capability: bool,
) -> domain.CapabilityResolution | None:
    if isinstance(resolution, SpellAttackResolutionSchema):
        return domain.AttackResolution(
            modes=(resolution.mode,),
            attack_bonus=domain.DerivedAttackBonus("spell_attack_modifier"),
            hit=outcome,
            miss=domain.Outcome(
                tuple(
                    compile_capability_effect(effect)
                    for effect in miss_values
                    if is_compilable_effect(effect)
                ),
                miss_ends_capability,
            ),
            attacks=resolution.attacks,
            allocation=resolution.allocation,
        )
    if isinstance(resolution, AutomaticResolutionSchema):
        return domain.AutomaticResolution(outcome)
    if resolution.ability is None:
        return None
    difficulty = resolution.difficulty
    if isinstance(difficulty, FixedDifficultyClassSchema):
        compiled_difficulty: domain.DifficultyClass = domain.FixedDifficultyClass(
            difficulty.value
        )
    else:
        derived = cast(DerivedDifficultyClassSchema, difficulty)
        compiled_difficulty = domain.DerivedDifficultyClass(derived.type)
    return domain.SavingThrowResolution(
        ability=normalize_save_ability(resolution.ability),
        difficulty=compiled_difficulty,
        failure=(
            domain.OutcomeStage(
                outcome.effects,
                (_compile_repeat_save(resolution.repeat_save, resolution.ability),)
                if resolution.repeat_save is not None
                else (),
            ),
        ),
        success=domain.Outcome(
            tuple(
                compile_capability_effect(effect)
                for effect in success_values
                if is_compilable_effect(effect)
            ),
            success_ends_capability,
        ),
        success_damage=resolution.success_damage,
        automatic_success=tuple(
            _compile_spell_requirement(requirement)
            for requirement in resolution.automatic_success
        ),
        automatic_failure=tuple(
            _compile_spell_requirement(requirement)
            for requirement in resolution.automatic_failure
        ),
        save_modifiers=tuple(
            _compile_save_modifier(modifier) for modifier in resolution.save_modifiers
        ),
    )


def _compile_triggers(raw: SpellSchema) -> tuple[domain.CapabilityTrigger, ...]:
    assert raw.capability is not None
    compiled: list[domain.CapabilityTrigger] = []
    for trigger in raw.capability.outcome_triggers:
        resolution = trigger.resolution.root
        if not isinstance(
            resolution,
            (
                AutomaticResolutionSchema,
                SavingThrowResolutionSchema,
                SpellAttackResolutionSchema,
            ),
        ):
            continue
        outcome = (
            resolution.failure
            if isinstance(resolution, SavingThrowResolutionSchema)
            else resolution.hit
            if isinstance(resolution, SpellAttackResolutionSchema)
            else resolution.outcome
        )
        nested = compile_definition(raw.capability.target, resolution, outcome)
        if nested is None:
            continue
        compiled.append(
            domain.CapabilityTrigger(
                event=trigger.event,
                resolution=nested.resolution,
                requirements=tuple(
                    _compile_spell_requirement(requirement)
                    for requirement in trigger.requirements
                ),
            )
        )
    return tuple(compiled)


def _compile_follow_ups(raw: SpellSchema) -> tuple[domain.CapabilityStep, ...]:
    assert raw.capability is not None
    outer = raw.capability.resolution.root
    if not isinstance(outer, SequenceResolutionSchema):
        return ()
    compiled: list[domain.CapabilityStep] = []
    for step in outer.steps[1:]:
        resolution = step.resolution.root
        if not isinstance(
            resolution,
            (
                AutomaticResolutionSchema,
                SavingThrowResolutionSchema,
                SpellAttackResolutionSchema,
            ),
        ):
            continue
        outcome = (
            resolution.failure
            if isinstance(resolution, SavingThrowResolutionSchema)
            else resolution.hit
            if isinstance(resolution, SpellAttackResolutionSchema)
            else resolution.outcome
        )
        nested = compile_definition(
            step.target or raw.capability.target,
            resolution,
            outcome,
        )
        if nested is not None:
            compiled.append(domain.CapabilityStep(nested.target, nested.resolution))
    return tuple(compiled)


def _compile_repeat_save(
    repeat: RepeatSaveProgressionSchema,
    default_ability: str,
) -> domain.RepeatSave:
    failure_effects: tuple[domain.CapabilityEffect, ...] = ()
    if repeat.on_failure is not None:
        failure = repeat.on_failure.root
        if isinstance(failure, AutomaticResolutionSchema):
            failure_effects = tuple(
                compile_capability_effect(effect.root)
                for effect in failure.outcome.effects
                if is_compilable_effect(effect.root)
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


def _compile_spell_requirement(value: object) -> domain.CapabilityRequirement:
    if isinstance(
        value,
        (
            ConditionRequirementSchema,
            CreatureTypeRequirementSchema,
            NotAffectedRequirementSchema,
            SizeRequirementSchema,
        ),
    ):
        return compile_requirement(value)
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


def _compile_save_modifier(
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
        duration=compile_duration(value.duration),
        requirements=tuple(
            _compile_spell_requirement(requirement)
            for requirement in value.requirements
        ),
    )


def _compile_target(
    target: SpellTargetSchema,
) -> domain.CapabilityTarget | None:
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
        return None
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
