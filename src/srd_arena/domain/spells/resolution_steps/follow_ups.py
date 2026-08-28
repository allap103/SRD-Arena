"""Resolve secondary steps that originate from a spell's primary target."""

from typing import cast

from ...capabilities import CapabilityStep, DamageEffect, SavingThrowResolution
from ...rolls.dice import resolve_dice
from ...rolls.saving_throws import (
    Ability,
    SavingThrowCreature,
    resolve_saving_throw,
)
from ..definitions import SpellDamage
from .context import SpellActionContext
from .scaling import (
    parse_damage_dice,
    resource_dice_increment,
    scaled_damage_dice,
)


def resolve_follow_up(
    context: SpellActionContext,
    follow_up: CapabilityStep,
    cast_level: int,
    sequence_step: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Resolve a persistent spell's scheduled damage or saving-throw step.

    A follow-up without target-origin area geometry is intentionally skipped.

    >>> from types import SimpleNamespace
    >>> from ...capabilities import AutomaticResolution, CapabilityStep
    >>> from ...capabilities import CapabilityTarget, Outcome
    >>> follow_up = CapabilityStep(
    ...     CapabilityTarget("self"), AutomaticResolution(Outcome())
    ... )
    >>> resolve_follow_up(SimpleNamespace(), follow_up, 1, 2)
    ([], [])
    """

    if (
        follow_up.target.kind != "area"
        or follow_up.target.origin != "target"
        or follow_up.target.size_feet is None
        or context.area_targets_around is None
        or not isinstance(follow_up.resolution, SavingThrowResolution)
    ):
        return [], []
    assert context.creature.spellcasting is not None
    assert context.roller is not None
    targets = context.area_targets_around(
        context.target.target_ref,
        follow_up.target.size_feet,
    )
    damage_definitions = tuple(
        SpellDamage(effect.dice, effect.damage_type)
        for stage in follow_up.resolution.failure
        for effect in stage.effects
        if isinstance(effect, DamageEffect)
    )
    definition = context.spell.definition
    assert definition is not None
    if cast_level > context.spell.level:
        scaled: list[SpellDamage] = []
        for damage in damage_definitions:
            increment = resource_dice_increment(
                definition,
                "damage_dice",
                damage.damage_type,
            )
            if increment is None:
                scaled.append(damage)
                continue
            increment_count, increment_sides = parse_damage_dice(increment)
            scaled.append(
                SpellDamage(
                    scaled_damage_dice(
                        damage.dice,
                        increment_count,
                        increment_sides,
                        cast_level - context.spell.level,
                    ),
                    damage.damage_type,
                )
            )
        damage_definitions = tuple(scaled)
    shared_rolls = [
        (
            damage,
            resolve_dice(
                *parse_damage_dice(damage.dice),
                modifier=(
                    context.damage_roll_modifier_for()
                    if context.damage_roll_modifier_for is not None
                    else context.damage_roll_modifier
                ),
                roller=context.roller,
            ),
        )
        for damage in damage_definitions
    ]
    save_details: list[dict[str, object]] = []
    damage_details: list[dict[str, object]] = []
    ability = follow_up.resolution.ability
    for target in targets:
        save = resolve_saving_throw(
            cast(SavingThrowCreature, target.creature),
            cast(Ability, ability),
            context.creature.spellcasting.save_dc,
            mode=context.save_roll_modes.get(target.target_ref, "normal"),
            sourced_modifier_override=(
                context.save_roll_modifier_for(target.target_ref, ability)
                if context.save_roll_modifier_for is not None
                else context.save_roll_modifiers.get(target.target_ref)
            ),
            sourced_mode_override=(
                context.save_sourced_roll_mode_for(target.target_ref, ability)
                if context.save_sourced_roll_mode_for is not None
                else context.save_sourced_roll_modes.get(target.target_ref)
            ),
            roller=context.roller,
            automatic_failure_reasons=target.automatic_failure_reasons(ability),
        )
        save_details.append(
            {
                "sequence_step": sequence_step,
                "target_ref": target.target_ref,
                "target_label": target.target_label,
                "ability": ability,
                "die": save.check.roll.selected,
                "modifier": save.modifiers.total,
                "total": save.check.roll.total,
                "target_dc": save.check.target,
                "success": save.check.success,
                "automatic_failure_reasons": list(save.automatic_failure_reasons),
            }
        )
        for damage, roll in shared_rolls:
            final_damage = (
                roll.total // 2
                if save.check.success and follow_up.resolution.success_damage == "half"
                else 0
                if save.check.success
                else roll.total
            )
            applied = target.creature.take_damage(final_damage, damage.damage_type)
            damage_details.append(
                {
                    "sequence_step": sequence_step,
                    "target_ref": target.target_ref,
                    "target_label": target.target_label,
                    "dice": damage.dice,
                    "dice_values": [die.result for die in roll.dice],
                    "dice_total": roll.subtotal,
                    "modifier": roll.modifier,
                    "total": roll.total,
                    "damage_type": damage.damage_type,
                    "saved": save.check.success,
                    "final_damage": final_damage,
                    "applied_damage": applied,
                }
            )
    return save_details, damage_details
