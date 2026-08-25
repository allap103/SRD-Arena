"""Interpret an authored spell definition into a runtime resolution plan."""

from dataclasses import dataclass

from ...capabilities import (
    AutomaticResolution,
    CapabilityDefinition,
    CapabilityEffect,
    CapabilityResolution,
    ConditionEffect,
    ConditionImmunityRequirement,
    CreatureTraitRequirement,
    CreatureTypeRequirement,
    DamageEffect,
    HealingEffect,
    RepeatSave,
    RelationshipRequirement,
    RollModifierEffect,
    SavingThrowResolution,
    TemporaryHitPointsEffect,
    capability_effects,
    primary_effects,
)
from ...rolls.dice import DicePoolResult, resolve_dice
from ..definitions import SpellDamage
from .context import SpellActionContext, SpellTargetContext
from .details import roll_optional_dice
from .scaling import (
    actor_level_damage_dice,
    parse_damage_dice,
    resource_dice_increment,
    scale_dice,
)


@dataclass(frozen=True)
class PreparedSpellResolution:
    definition: CapabilityDefinition
    resolution: CapabilityResolution
    definition_effects: tuple[CapabilityEffect, ...]
    targets: tuple[SpellTargetContext, ...]
    cast_level: int
    levels_above: int
    save_ability: str | None
    half_damage_on_save: bool
    conditions: tuple[str, ...]
    automatic_failure_creature_types: tuple[str, ...]
    automatic_success_condition_immunities: tuple[str, ...]
    automatic_success_traits: tuple[str, ...]
    disadvantage_creature_types: tuple[str, ...]
    expires_on_source_turn_end: bool
    repeat_save: RepeatSave | None
    repeat_failure_conditions: tuple[str, ...]
    repeat_failure_damage: tuple[SpellDamage, ...]
    end_events: tuple[tuple[str, str], ...]
    damage_repeat_save_advantage: bool
    healing_effects: tuple[HealingEffect, ...]
    temporary_hit_point_effects: tuple[TemporaryHitPointsEffect, ...]
    roll_modifier_effects: tuple[RollModifierEffect, ...]
    damage_definitions: tuple[SpellDamage, ...]
    shared_damage_rolls: tuple[tuple[SpellDamage, DicePoolResult], ...]
    shared_healing_rolls: tuple[
        tuple[HealingEffect, str | None, DicePoolResult | None], ...
    ]


def prepare_spell_resolution(context: SpellActionContext) -> PreparedSpellResolution:
    spell = context.spell
    definition = spell.definition
    assert definition is not None
    assert context.roller is not None

    definition_effects = capability_effects(definition)
    resolved_effects = primary_effects(definition)
    resolution = definition.resolution
    save_ability = (
        resolution.ability if isinstance(resolution, SavingThrowResolution) else None
    )
    half_damage_on_save = (
        isinstance(resolution, SavingThrowResolution)
        and resolution.success_damage == "half"
    )
    conditions = tuple(
        effect.condition
        for effect in resolved_effects
        if isinstance(effect, ConditionEffect)
    )
    automatic_failure_creature_types = tuple(
        creature_type
        for requirement in (
            resolution.automatic_failure
            if isinstance(resolution, SavingThrowResolution)
            else ()
        )
        if isinstance(requirement, CreatureTypeRequirement)
        for creature_type in requirement.creature_types
    )
    automatic_success_condition_immunities = tuple(
        requirement.condition
        for requirement in (
            resolution.automatic_success
            if isinstance(resolution, SavingThrowResolution)
            else ()
        )
        if isinstance(requirement, ConditionImmunityRequirement)
    )
    automatic_success_traits = tuple(
        requirement.trait
        for requirement in (
            resolution.automatic_success
            if isinstance(resolution, SavingThrowResolution)
            else ()
        )
        if isinstance(requirement, CreatureTraitRequirement)
    )
    disadvantage_creature_types = tuple(
        creature_type
        for modifier in (
            resolution.save_modifiers
            if isinstance(resolution, SavingThrowResolution)
            else ()
        )
        if modifier.mode == "disadvantage"
        for requirement in modifier.requirements
        if isinstance(requirement, CreatureTypeRequirement)
        for creature_type in requirement.creature_types
    )
    expires_on_source_turn_end = any(
        isinstance(effect, ConditionEffect)
        and effect.duration is not None
        and effect.duration.kind == "end_of_turn"
        and effect.duration.creature == "source"
        for effect in resolved_effects
    )
    repeat_save = (
        next(
            (repeat for stage in resolution.failure for repeat in stage.repeat_saves),
            None,
        )
        if isinstance(resolution, SavingThrowResolution)
        else None
    )
    repeat_failure_conditions = tuple(
        effect.condition
        for effect in (repeat_save.failure_effects if repeat_save is not None else ())
        if isinstance(effect, ConditionEffect)
    )
    repeat_failure_damage = tuple(
        SpellDamage(effect.dice, effect.damage_type)
        for effect in (repeat_save.failure_effects if repeat_save is not None else ())
        if isinstance(effect, DamageEffect)
    )
    end_events = tuple(
        (
            trigger.event,
            (
                "source_team"
                if any(
                    isinstance(requirement, RelationshipRequirement)
                    and requirement.relationship == "ally_of_source"
                    for requirement in trigger.requirements
                )
                else "any"
            ),
        )
        for trigger in definition.triggers
        if isinstance(trigger.resolution, AutomaticResolution)
        and trigger.resolution.outcome.end_capability
    )
    damage_repeat_save_advantage = any(
        trigger.event == "target_damaged"
        and isinstance(trigger.resolution, SavingThrowResolution)
        and any(
            modifier.mode == "advantage"
            for modifier in trigger.resolution.save_modifiers
        )
        for trigger in definition.triggers
    )
    healing_effects = tuple(
        effect for effect in definition_effects if isinstance(effect, HealingEffect)
    )
    temporary_hit_point_effects = tuple(
        effect
        for effect in definition_effects
        if isinstance(effect, TemporaryHitPointsEffect)
    )
    roll_modifier_effects = tuple(
        effect
        for effect in definition_effects
        if isinstance(effect, RollModifierEffect)
    )

    damage_definitions = tuple(
        SpellDamage(effect.dice, effect.damage_type)
        for effect in resolved_effects
        if isinstance(effect, DamageEffect)
    )
    actor_damage_dice = actor_level_damage_dice(
        definition,
        context.creature.attributes.level,
    )
    if actor_damage_dice is not None:
        damage_definitions = tuple(
            SpellDamage(actor_damage_dice, damage.damage_type)
            for damage in damage_definitions
        )
    cast_level = context.cast_level if context.cast_level is not None else spell.level
    levels_above = cast_level - spell.level
    if levels_above > 0:
        scaled: list[SpellDamage] = []
        for damage in damage_definitions:
            slot_damage_increment = resource_dice_increment(
                definition,
                "damage_dice",
                damage.damage_type,
            )
            if slot_damage_increment is None:
                scaled.append(damage)
                continue
            increment_count, increment_sides = parse_damage_dice(slot_damage_increment)
            count, sides = parse_damage_dice(damage.dice)
            if sides != increment_sides:
                raise ValueError("Slot damage scaling must use the base damage die.")
            count += increment_count * levels_above
            scaled.append(SpellDamage(f"{count}d{sides}", damage.damage_type))
        damage_definitions = tuple(scaled)

    shared_damage_rolls: list[tuple[SpellDamage, DicePoolResult]] = []
    if isinstance(resolution, SavingThrowResolution):
        for damage in damage_definitions:
            count, sides = parse_damage_dice(damage.dice)
            shared_damage_rolls.append(
                (
                    damage,
                    resolve_dice(
                        count,
                        sides,
                        modifier=(
                            context.damage_roll_modifier_for()
                            if context.damage_roll_modifier_for is not None
                            else context.damage_roll_modifier
                        ),
                        roller=context.roller,
                    ),
                )
            )
    shared_healing_rolls = tuple(
        (
            healing,
            dice,
            roll_optional_dice(dice, context.roller),
        )
        for healing in healing_effects
        if healing.pool is None
        for dice in (
            scale_dice(
                healing.dice,
                resource_dice_increment(definition, "healing_dice"),
                levels_above,
            ),
        )
    )
    return PreparedSpellResolution(
        definition=definition,
        resolution=resolution,
        definition_effects=definition_effects,
        targets=context.targets or (context.target,),
        cast_level=cast_level,
        levels_above=levels_above,
        save_ability=save_ability,
        half_damage_on_save=half_damage_on_save,
        conditions=conditions,
        automatic_failure_creature_types=automatic_failure_creature_types,
        automatic_success_condition_immunities=(
            automatic_success_condition_immunities
        ),
        automatic_success_traits=automatic_success_traits,
        disadvantage_creature_types=disadvantage_creature_types,
        expires_on_source_turn_end=expires_on_source_turn_end,
        repeat_save=repeat_save,
        repeat_failure_conditions=repeat_failure_conditions,
        repeat_failure_damage=repeat_failure_damage,
        end_events=end_events,
        damage_repeat_save_advantage=damage_repeat_save_advantage,
        healing_effects=healing_effects,
        temporary_hit_point_effects=temporary_hit_point_effects,
        roll_modifier_effects=roll_modifier_effects,
        damage_definitions=damage_definitions,
        shared_damage_rolls=tuple(shared_damage_rolls),
        shared_healing_rolls=shared_healing_rolls,
    )
