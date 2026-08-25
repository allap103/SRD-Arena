"""Resolve attacks, saves, damage, and restoration for each spell target."""

from dataclasses import dataclass
from typing import cast

from ...capabilities import (
    AttackResolution,
    AutomaticResolution,
    SavingThrowResolution,
)
from ...rolls.dice import resolve_check, resolve_d20, resolve_dice
from ...rolls.saving_throws import (
    Ability,
    SavingThrowCreature,
    resolve_saving_throw,
)
from .context import SpellActionContext, SpellTargetContext
from .details import restoration_detail, roll_optional_dice
from .preparation import PreparedSpellResolution
from .scaling import parse_damage_dice, resource_int_increment


@dataclass
class ResolvedSpellTargets:
    messages: list[tuple[str, str]]
    save_details: list[dict[str, object]]
    attack_details: list[dict[str, object]]
    damage_details: list[dict[str, object]]
    healing_details: list[dict[str, object]]
    temporary_hit_point_details: list[dict[str, object]]
    affected_targets: list[SpellTargetContext]


def resolve_spell_targets(
    context: SpellActionContext,
    prepared: PreparedSpellResolution,
) -> ResolvedSpellTargets:
    spell = context.spell
    assert context.creature.spellcasting is not None
    assert context.roller is not None

    target_suffix = (
        f" on {prepared.targets[0].target_label}"
        if prepared.definition.target.kind == "creature"
        and len(prepared.targets) == 1
        else ""
    )
    messages = [
        (
            "system",
            f"{context.creature.name} casts {spell.name}{target_suffix}.",
        )
    ]
    save_details: list[dict[str, object]] = []
    attack_details: list[dict[str, object]] = []
    damage_details: list[dict[str, object]] = []
    healing_details: list[dict[str, object]] = []
    temporary_hit_point_details: list[dict[str, object]] = []
    affected_targets: list[SpellTargetContext] = []

    for target in prepared.targets:
        successful_save = False
        automatic_success_reasons: tuple[str, ...] = ()
        hit = True
        target_damage_rolls = list(prepared.shared_damage_rolls)
        if isinstance(prepared.resolution, SavingThrowResolution):
            ability = prepared.save_ability or "dexterity"
            creature_type = (target.creature.statistics.creature_type or "").casefold()
            automatic_reasons = target.automatic_failure_reasons(ability)
            automatic_success_reasons = tuple(
                f"{spell.name}: immune to {condition}"
                for condition in prepared.automatic_success_condition_immunities
                if any(
                    immunity.value == condition
                    for immunity in target.creature.statistics.condition_immunities
                )
            )
            automatic_success_reasons += tuple(
                f"{spell.name}: {trait}"
                for trait in prepared.automatic_success_traits
                if trait in target.creature.statistics.mechanical_traits
            )
            if creature_type in prepared.automatic_failure_creature_types:
                automatic_reasons += (f"{spell.name}: {creature_type}",)
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
                save_details.append(
                    {
                        "target_ref": target.target_ref,
                        "target_label": target.target_label,
                        "ability": ability,
                        "target_dc": context.creature.spellcasting.save_dc,
                        "success": True,
                        "automatic_success_reasons": list(automatic_success_reasons),
                        "automatic_failure_reasons": [],
                    }
                )
            else:
                save = resolve_saving_throw(
                    cast(SavingThrowCreature, target.creature),
                    cast(Ability, ability),
                    context.creature.spellcasting.save_dc,
                    mode=save_mode,
                    roller=context.roller,
                    automatic_failure_reasons=automatic_reasons,
                )
                successful_save = save.check.success
                save_details.append(
                    {
                        "target_ref": target.target_ref,
                        "target_label": target.target_label,
                        "ability": ability,
                        "die": save.check.roll.selected,
                        "modifier": save.modifiers.total,
                        "total": save.check.roll.total,
                        "target_dc": save.check.target,
                        "success": successful_save,
                        "automatic_success_reasons": list(automatic_success_reasons),
                        "automatic_failure_reasons": list(
                            save.automatic_failure_reasons
                        ),
                    }
                )
        elif isinstance(prepared.resolution, AttackResolution):
            attack = resolve_d20(
                modifier=context.creature.spellcasting.attack_bonus,
                mode=context.attack_roll_modes.get(target.target_ref, "normal"),
                roller=context.roller,
            )
            check = resolve_check(attack, target.creature.get_armor_class())
            hit = attack.selected != 1 and (attack.selected == 20 or check.success)
            automatic_critical = context.automatic_critical_providers.get(
                target.target_ref, ()
            )
            critical_hit = hit and (attack.selected == 20 or bool(automatic_critical))
            attack_details.append(
                {
                    "projectile_index": len(attack_details) + 1,
                    "target_ref": target.target_ref,
                    "target_label": target.target_label,
                    "die": attack.selected,
                    "modifier": context.creature.spellcasting.attack_bonus,
                    "total": attack.total,
                    "target_ac": target.creature.get_armor_class(),
                    "hit": hit,
                    "critical_hit": critical_hit,
                    "automatic_critical_provider_ids": list(automatic_critical),
                }
            )
            for damage in prepared.damage_definitions:
                count, sides = parse_damage_dice(damage.dice)
                if critical_hit:
                    count *= 2
                target_damage_rolls.append(
                    (damage, resolve_dice(count, sides, roller=context.roller))
                )

        target_damage = 0
        for damage, roll in target_damage_rolls:
            final_damage = roll.total
            if successful_save:
                final_damage = (
                    final_damage // 2 if prepared.half_damage_on_save else 0
                )
            if isinstance(prepared.resolution, AttackResolution) and not hit:
                final_damage = 0
            applied = target.creature.take_damage(final_damage, damage.damage_type)
            target_damage += applied
            damage_details.append(
                {
                    "target_ref": target.target_ref,
                    "target_label": target.target_label,
                    "dice": f"{len(roll.dice)}d{roll.dice[0].sides}",
                    "dice_values": [die.result for die in roll.dice],
                    "dice_total": roll.subtotal,
                    "modifier": roll.modifier,
                    "total": roll.total,
                    "damage_type": damage.damage_type,
                    "saved": successful_save,
                    "final_damage": final_damage,
                    "applied_damage": applied,
                }
            )

        affected = (
            isinstance(prepared.resolution, SavingThrowResolution)
            and not successful_save
        ) or (
            isinstance(
                prepared.resolution,
                (AttackResolution, AutomaticResolution),
            )
            and hit
        )
        if affected:
            affected_targets.append(target)
            for healing, dice, healing_roll in prepared.shared_healing_rolls:
                modifier = healing.bonus + (
                    context.creature.spellcasting.ability_modifier
                    if healing.modifier == "ability_modifier"
                    else 0
                )
                modifier += (
                    resource_int_increment(prepared.definition, "healing_bonus")
                    * prepared.levels_above
                )
                total = (
                    target.creature.get_max_health() - target.creature.get_health()
                    if healing.restore_to_maximum
                    else max(
                        0,
                        (healing_roll.subtotal if healing_roll is not None else 0)
                        + modifier,
                    )
                )
                applied = target.creature.heal(total)
                healing_details.append(
                    restoration_detail(
                        target,
                        dice=dice,
                        roll=healing_roll,
                        modifier=modifier,
                        total=total,
                        applied=applied,
                    )
                )
            for healing in prepared.healing_effects:
                if healing.pool is None:
                    continue
                allocated = context.healing_allocations.get(target.target_ref, 0)
                applied = target.creature.heal(allocated)
                detail = restoration_detail(
                    target,
                    dice=None,
                    roll=None,
                    modifier=0,
                    total=allocated,
                    applied=applied,
                )
                detail["allocated"] = allocated
                healing_details.append(detail)
            for temporary in prepared.temporary_hit_point_effects:
                if temporary.trigger != "application":
                    continue
                temporary_roll = roll_optional_dice(temporary.dice, context.roller)
                modifier = temporary.value + (
                    context.creature.spellcasting.ability_modifier
                    if temporary.modifier == "ability_modifier"
                    else 0
                )
                modifier += (
                    resource_int_increment(
                        prepared.definition,
                        "temporary_hit_points",
                    )
                    * prepared.levels_above
                )
                total = max(
                    0,
                    (temporary_roll.subtotal if temporary_roll is not None else 0)
                    + modifier,
                )
                granted = target.creature.grant_temporary_hit_points(total)
                temporary_hit_point_details.append(
                    restoration_detail(
                        target,
                        dice=temporary.dice,
                        roll=temporary_roll,
                        modifier=modifier,
                        total=total,
                        applied=granted,
                    )
                )

        outcome = (
            "damages"
            if target_damage > 0
            else "heals"
            if any(
                detail["target_ref"] == target.target_ref for detail in healing_details
            )
            else "wards"
            if any(
                detail["target_ref"] == target.target_ref
                for detail in temporary_hit_point_details
            )
            else "affects"
            if affected and prepared.conditions
            else "does not affect"
        )
        if not spell.removable_conditions:
            if automatic_success_reasons:
                messages.append(
                    (
                        "system",
                        f"{target.target_label} is unaffected by {spell.name}: "
                        f"{'; '.join(automatic_success_reasons)}.",
                    )
                )
            elif (
                isinstance(prepared.resolution, SavingThrowResolution)
                and successful_save
                and target_damage == 0
            ):
                messages.append(
                    (
                        "system",
                        f"{target.target_label} resists {spell.name} with a "
                        f"successful {(prepared.save_ability or 'dexterity').title()} "
                        "save.",
                    )
                )
            else:
                messages.append(
                    ("system", f"{spell.name} {outcome} {target.target_label}.")
                )

    return ResolvedSpellTargets(
        messages=messages,
        save_details=save_details,
        attack_details=attack_details,
        damage_details=damage_details,
        healing_details=healing_details,
        temporary_hit_point_details=temporary_hit_point_details,
        affected_targets=affected_targets,
    )
