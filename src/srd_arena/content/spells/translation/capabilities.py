from dataclasses import replace
from typing import cast

from srd_arena.content.capabilities import (
    DerivedDifficultyClassSchema,
    FixedDifficultyClassSchema,
)
import srd_arena.domain.capabilities as domain

from srd_arena.content.spells.resolution import (
    AutomaticResolutionSchema,
    OutcomeSchema,
    RepeatResolutionSchema,
    SavingThrowResolutionSchema,
    SequenceResolutionSchema,
    SpellAttackResolutionSchema,
)
from srd_arena.content.spells.schema import SpellSchema
from srd_arena.content.spells.targeting import SpellTargetSchema
from srd_arena.content.spells.targeting import (
    AreaSpellTargetSchema,
    CreatureSpellTargetSchema,
)

from .scaling import compile_scaling
from .effects import compile_capability_effect, is_compilable_effect

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
    definition = compile_definition(raw.capability.target, resolution, outcome)
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
    )


def compile_definition(
    target: SpellTargetSchema,
    resolution: SpellResolutionSchema,
    outcome: OutcomeSchema,
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
        )
    )
    compiled_resolution = _compile_resolution(
        resolution,
        compiled_outcome,
        success_values,
        miss_values,
    )
    if compiled_resolution is None:
        return None
    return domain.CapabilityDefinition(compiled_target, compiled_resolution)


def _compile_resolution(
    resolution: SpellResolutionSchema,
    outcome: domain.Outcome,
    success_values: tuple[object, ...],
    miss_values: tuple[object, ...],
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
                )
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
        ability=resolution.ability,
        difficulty=compiled_difficulty,
        failure=(domain.OutcomeStage(outcome.effects),),
        success=domain.Outcome(
            tuple(
                compile_capability_effect(effect)
                for effect in success_values
                if is_compilable_effect(effect)
            )
        ),
        success_damage=resolution.success_damage,
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
