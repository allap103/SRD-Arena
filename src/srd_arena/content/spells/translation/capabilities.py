from typing import cast

from srd_arena.content.capabilities import (
    DerivedDifficultyClassSchema,
    FixedDifficultyClassSchema,
)
from srd_arena.content.capabilities.compiler import compile_effect, is_shared_effect
import srd_arena.domain.capabilities as domain

from srd_arena.content.spells.resolution import (
    AutomaticResolutionSchema,
    OutcomeSchema,
    SavingThrowResolutionSchema,
    SpellAttackResolutionSchema,
)
from srd_arena.content.spells.targeting import SpellTargetSchema

SpellResolutionSchema = (
    AutomaticResolutionSchema
    | SavingThrowResolutionSchema
    | SpellAttackResolutionSchema
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
        is_shared_effect(effect)
        for effect in (*effect_values, *success_values, *miss_values)
    ):
        return None
    compiled_target = _compile_target(target)
    if compiled_target is None:
        return None
    compiled_outcome = domain.Outcome(
        tuple(
            compile_effect(effect)
            for effect in effect_values
            if is_shared_effect(effect)
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
                    compile_effect(effect)
                    for effect in miss_values
                    if is_shared_effect(effect)
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
                compile_effect(effect)
                for effect in success_values
                if is_shared_effect(effect)
            )
        ),
        success_damage=resolution.success_damage,
    )


def _compile_target(
    target: SpellTargetSchema,
) -> domain.CapabilityTarget | None:
    if target.type == "self":
        return domain.CapabilityTarget(kind="self")
    if target.type == "creature":
        return domain.CapabilityTarget(kind="creature")
    if target.type != "area":
        return None
    geometry = target.geometry
    return domain.CapabilityTarget(
        kind="area",
        shape=geometry.shape,
        size_feet=(
            geometry.radius_feet
            or geometry.length_feet
            or geometry.diameter_feet
        ),
        width_feet=geometry.width_feet,
        origin=target.origin,
    )
