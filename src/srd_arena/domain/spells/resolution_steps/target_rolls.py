"""Resolve the save or attack roll for one spell target."""

from dataclasses import dataclass
from typing import cast

from ...capabilities import AttackResolution, SavingThrowResolution
from ...rolls.dice import DicePoolResult, resolve_check, resolve_d20, resolve_dice
from ...rolls.saving_throws import (
    Ability,
    SavingThrowCreature,
    resolve_saving_throw,
)
from ..definitions import SpellDamage
from .context import SpellActionContext, SpellTargetContext
from .preparation import PreparedSpellResolution
from .scaling import parse_damage_dice


@dataclass
class TargetRollOutcome:
    """Collect one target's save/attack result and resulting damage rolls."""

    successful_save: bool
    automatic_success_reasons: tuple[str, ...]
    hit: bool
    damage_rolls: list[tuple[SpellDamage, DicePoolResult]]
    save_detail: dict[str, object] | None = None
    attack_detail: dict[str, object] | None = None


def resolve_target_roll(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
    target: SpellTargetContext,
    *,
    projectile_index: int,
) -> TargetRollOutcome:
    """Resolve the attack roll or saving throw required for one spell target."""

    assert context.creature.spellcasting is not None
    assert context.roller is not None

    successful_save = False
    automatic_success_reasons: tuple[str, ...] = ()
    hit = True
    damage_rolls = list(prepared.shared_damage_rolls)
    save_detail: dict[str, object] | None = None
    attack_detail: dict[str, object] | None = None

    if isinstance(prepared.resolution, SavingThrowResolution):
        ability = prepared.save_ability or "dexterity"
        creature_type = (target.creature.statistics.creature_type or "").casefold()
        automatic_reasons = target.automatic_failure_reasons(ability)
        automatic_success_reasons = tuple(
            f"{context.spell.name}: immune to {condition}"
            for condition in prepared.automatic_success_condition_immunities
            if any(
                immunity.value == condition
                for immunity in target.creature.statistics.condition_immunities
            )
        )
        automatic_success_reasons += tuple(
            f"{context.spell.name}: {trait}"
            for trait in prepared.automatic_success_traits
            if trait in target.creature.statistics.mechanical_traits
        )
        if creature_type in prepared.automatic_failure_creature_types:
            automatic_reasons += (f"{context.spell.name}: {creature_type}",)
        save_mode = context.save_roll_modes.get(
            target.target_ref,
            (
                "disadvantage"
                if creature_type in prepared.disadvantage_creature_types
                else "normal"
            ),
        )
        if automatic_success_reasons:
            successful_save = True
            save_detail = {
                "target_ref": target.target_ref,
                "target_label": target.target_label,
                "ability": ability,
                "target_dc": context.creature.spellcasting.save_dc,
                "success": True,
                "automatic_success_reasons": list(automatic_success_reasons),
                "automatic_failure_reasons": [],
            }
        else:
            save = resolve_saving_throw(
                cast(SavingThrowCreature, target.creature),
                cast(Ability, ability),
                context.creature.spellcasting.save_dc,
                mode=save_mode,
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
                automatic_failure_reasons=automatic_reasons,
            )
            successful_save = save.check.success
            save_detail = {
                "target_ref": target.target_ref,
                "target_label": target.target_label,
                "ability": ability,
                "die": save.check.roll.selected,
                "modifier": save.modifiers.total,
                "total": save.check.roll.total,
                "target_dc": save.check.target,
                "success": successful_save,
                "automatic_success_reasons": list(automatic_success_reasons),
                "automatic_failure_reasons": list(save.automatic_failure_reasons),
            }
    elif isinstance(prepared.resolution, AttackResolution):
        attack = resolve_d20(
            modifier=(
                context.creature.spellcasting.attack_bonus
                + (
                    context.attack_roll_modifier_for(target.target_ref)
                    if context.attack_roll_modifier_for is not None
                    else context.attack_roll_modifiers.get(target.target_ref, 0)
                )
            ),
            mode=context.attack_roll_modes.get(target.target_ref, "normal"),
            roller=context.roller,
        )
        target_ac = context.target_armor_classes.get(
            target.target_ref,
            target.creature.get_armor_class(),
        )
        check = resolve_check(attack, target_ac)
        hit = attack.selected != 1 and (attack.selected == 20 or check.success)
        automatic_critical = context.automatic_critical_providers.get(
            target.target_ref, ()
        )
        critical_hit = hit and (attack.selected == 20 or bool(automatic_critical))
        attack_modifier = attack.total - attack.selected
        attack_detail = {
            "projectile_index": projectile_index,
            "target_ref": target.target_ref,
            "target_label": target.target_label,
            "die": attack.selected,
            "modifier": attack_modifier,
            "total": attack.total,
            "target_ac": target_ac,
            "hit": hit,
            "critical_hit": critical_hit,
            "automatic_critical_provider_ids": list(automatic_critical),
        }
        for damage in prepared.damage_definitions:
            count, sides = parse_damage_dice(damage.dice)
            if critical_hit:
                count *= 2
            damage_rolls.append(
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

    return TargetRollOutcome(
        successful_save=successful_save,
        automatic_success_reasons=automatic_success_reasons,
        hit=hit,
        damage_rolls=damage_rolls,
        save_detail=save_detail,
        attack_detail=attack_detail,
    )
