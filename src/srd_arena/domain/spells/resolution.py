from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import re
from typing import cast

from ..creatures import Creature
from ..creatures.feature_rules.types import CapabilityActionResult
from ..effects.results import EffectResult
from ..geometry import AreaOfEffect, serialize_area
from ..rolls.dice import DicePoolResult, resolve_dice
from ..rolls.dice import D20RollMode
from ..rolls.dice import resolve_check, resolve_d20
from ..rolls.saving_throws import (
    Ability,
    SavingThrowCreature,
    resolve_saving_throw,
)
from .definitions import FollowUpSpellResolution, Spell, SpellDamage

DieRoller = Callable[[int], int]


@dataclass(frozen=True)
class SpellTargetContext:
    creature: Creature
    target_ref: str
    target_label: str
    target_conditions: tuple[str, ...] = ()
    automatic_save_failures: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def automatic_failure_reasons(self, ability: str) -> tuple[str, ...]:
        return self.automatic_save_failures.get(ability, ())


@dataclass(frozen=True)
class SpellActionContext:
    creature: Creature
    spell: Spell
    target: SpellTargetContext
    current_round: int
    targets: tuple[SpellTargetContext, ...] = ()
    area: AreaOfEffect | None = None
    source_ref: str = "player"
    roller: DieRoller | None = None
    selected_condition: str | None = None
    selected_damage_type: str | None = None
    attack_roll_modes: dict[str, D20RollMode] = field(default_factory=dict)
    automatic_critical_providers: dict[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    cast_level: int | None = None
    save_roll_modes: dict[str, D20RollMode] = field(default_factory=dict)
    area_targets_around: (
        Callable[[str, int], tuple[SpellTargetContext, ...]] | None
    ) = None
    healing_allocations: dict[str, int] = field(default_factory=dict)


def resolve_spell_action(
    context: SpellActionContext,
) -> CapabilityActionResult | None:
    spell = context.spell
    if spell.mechanics is not None:
        return _resolve_immediate_spell(context)
    return None


def _resolve_immediate_spell(context: SpellActionContext) -> CapabilityActionResult:
    spell = context.spell
    mechanics = spell.mechanics
    assert mechanics is not None
    assert context.creature.spellcasting is not None
    assert context.roller is not None
    targets = context.targets or (context.target,)
    target_suffix = (
        f" on {targets[0].target_label}"
        if mechanics.target == "creature" and len(targets) == 1
        else ""
    )
    messages = [
        (
            "system",
            f"{context.creature.name} casts {spell.name}{target_suffix}.",
        )
    ]
    shared_damage_rolls: list[tuple[SpellDamage, DicePoolResult]] = []
    damage_definitions = mechanics.damage
    if mechanics.cantrip_damage_by_level:
        caster_level = context.creature.attributes.level
        scaled_dice = max(
            dice
            for level, dice in mechanics.cantrip_damage_by_level
            if level <= caster_level
        )
        damage_definitions = tuple(
            SpellDamage(scaled_dice, damage.damage_type) for damage in mechanics.damage
        )
    cast_level = context.cast_level if context.cast_level is not None else spell.level
    if mechanics.slot_damage_increment is not None and cast_level > spell.level:
        increment_count, increment_sides = _parse_damage_dice(
            mechanics.slot_damage_increment
        )
        scaled: list[SpellDamage] = []
        for damage in damage_definitions:
            count, sides = _parse_damage_dice(damage.dice)
            if sides != increment_sides:
                raise ValueError("Slot damage scaling must use the base damage die.")
            count += increment_count * (cast_level - spell.level)
            scaled.append(SpellDamage(f"{count}d{sides}", damage.damage_type))
        damage_definitions = tuple(scaled)
    if mechanics.resolution == "saving_throw":
        for damage in damage_definitions:
            count, sides = _parse_damage_dice(damage.dice)
            shared_damage_rolls.append(
                (damage, resolve_dice(count, sides, roller=context.roller))
            )
    shared_healing_rolls = tuple(
        (
            healing,
            dice,
            _roll_optional_dice(dice, context.roller),
        )
        for healing in mechanics.healing
        if healing.pool is None
        for dice in (
            _scale_dice(
                healing.dice,
                mechanics.slot_healing_dice_increment,
                cast_level - spell.level,
            ),
        )
    )

    save_details: list[dict[str, object]] = []
    attack_details: list[dict[str, object]] = []
    damage_details: list[dict[str, object]] = []
    healing_details: list[dict[str, object]] = []
    temporary_hit_point_details: list[dict[str, object]] = []
    affected_targets: list[SpellTargetContext] = []
    for target in targets:
        successful_save = False
        hit = True
        target_damage_rolls = list(shared_damage_rolls)
        if mechanics.resolution == "saving_throw":
            ability = mechanics.save_ability or "dexterity"
            creature_type = (target.creature.statistics.creature_type or "").casefold()
            automatic_reasons = target.automatic_failure_reasons(ability)
            automatic_success_reasons = tuple(
                f"{spell.name}: immune to {condition}"
                for condition in mechanics.automatic_success_condition_immunities
                if any(
                    immunity.value == condition
                    for immunity in target.creature.statistics.condition_immunities
                )
            )
            automatic_success_reasons += tuple(
                f"{spell.name}: {trait}"
                for trait in mechanics.automatic_success_traits
                if trait in target.creature.statistics.mechanical_traits
            )
            if creature_type in mechanics.automatic_failure_creature_types:
                automatic_reasons += (f"{spell.name}: {creature_type}",)
            save_mode = context.save_roll_modes.get(
                target.target_ref,
                "disadvantage"
                if creature_type in mechanics.disadvantage_creature_types
                else "normal",
            )
            save = resolve_saving_throw(
                cast(SavingThrowCreature, target.creature),
                cast(Ability, ability),
                context.creature.spellcasting.save_dc,
                mode=save_mode,
                roller=context.roller,
                automatic_failure_reasons=automatic_reasons,
            )
            successful_save = bool(automatic_success_reasons) or save.check.success
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
                    "automatic_failure_reasons": list(save.automatic_failure_reasons),
                }
            )
        elif mechanics.resolution == "spell_attack":
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
            for damage in damage_definitions:
                count, sides = _parse_damage_dice(damage.dice)
                if critical_hit:
                    count *= 2
                target_damage_rolls.append(
                    (damage, resolve_dice(count, sides, roller=context.roller))
                )
        target_damage = 0
        for damage, roll in target_damage_rolls:
            final_damage = roll.total
            if successful_save:
                final_damage = final_damage // 2 if mechanics.half_damage_on_save else 0
            if mechanics.resolution == "spell_attack" and not hit:
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
        affected = (mechanics.resolution == "saving_throw" and not successful_save) or (
            mechanics.resolution in {"spell_attack", "automatic"} and hit
        )
        if affected:
            affected_targets.append(target)
            for healing, dice, healing_roll in shared_healing_rolls:
                modifier = healing.bonus + (
                    context.creature.spellcasting.ability_modifier
                    if healing.add_spellcasting_modifier
                    else 0
                )
                modifier += mechanics.slot_healing_bonus_increment * (
                    cast_level - spell.level
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
                    _restoration_detail(
                        target,
                        dice=dice,
                        roll=healing_roll,
                        modifier=modifier,
                        total=total,
                        applied=applied,
                    )
                )
            for healing in mechanics.healing:
                if healing.pool is None:
                    continue
                allocated = context.healing_allocations.get(target.target_ref, 0)
                applied = target.creature.heal(allocated)
                detail = _restoration_detail(
                    target,
                    dice=None,
                    roll=None,
                    modifier=0,
                    total=allocated,
                    applied=applied,
                )
                detail["allocated"] = allocated
                healing_details.append(detail)
            for temporary in mechanics.temporary_hit_points:
                temporary_roll = _roll_optional_dice(temporary.dice, context.roller)
                modifier = temporary.value + (
                    context.creature.spellcasting.ability_modifier
                    if temporary.add_spellcasting_modifier
                    else 0
                )
                modifier += mechanics.slot_temporary_hit_points_increment * (
                    cast_level - spell.level
                )
                total = max(
                    0,
                    (temporary_roll.subtotal if temporary_roll is not None else 0)
                    + modifier,
                )
                granted = target.creature.grant_temporary_hit_points(total)
                temporary_hit_point_details.append(
                    _restoration_detail(
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
            if any(detail["target_ref"] == target.target_ref for detail in healing_details)
            else "wards"
            if any(
                detail["target_ref"] == target.target_ref
                for detail in temporary_hit_point_details
            )
            else "affects"
            if affected and mechanics.conditions
            else "does not affect"
        )
        if not spell.removable_conditions:
            messages.append(
                ("system", f"{spell.name} {outcome} {target.target_label}.")
            )

    for sequence_step, follow_up in enumerate(
        mechanics.follow_up_resolutions,
        start=2,
    ):
        follow_up_saves, follow_up_damage = _resolve_follow_up(
            context,
            follow_up,
            cast_level,
            sequence_step,
        )
        save_details.extend(follow_up_saves)
        damage_details.extend(follow_up_damage)

    effects: list[EffectResult] = []
    selected_condition = context.selected_condition
    if selected_condition not in mechanics.conditions:
        selected_condition = mechanics.conditions[0] if mechanics.conditions else None
    selected_conditions = (
        ((selected_condition,) if selected_condition is not None else ())
        if mechanics.condition_choice
        else mechanics.conditions
    )
    parent_kind = "concentration" if mechanics.concentration else "spell"
    maximum_hit_point_modifier = mechanics.maximum_hit_point_modifier + (
        mechanics.slot_maximum_hit_point_increment * (cast_level - spell.level)
    )
    selected_damage_resistances = mechanics.damage_resistances
    if mechanics.damage_resistance_choice:
        selected_damage_resistances = (
            (context.selected_damage_type,)
            if context.selected_damage_type in mechanics.damage_resistances
            else mechanics.damage_resistances[:1]
        )
    selected_damage_reduction_type = None
    if mechanics.damage_reduction_types:
        selected_damage_reduction_type = (
            context.selected_damage_type
            if context.selected_damage_type in mechanics.damage_reduction_types
            else mechanics.damage_reduction_types[0]
        )
    if (
        affected_targets
        and (
            mechanics.conditions
            or maximum_hit_point_modifier != 0
            or selected_damage_resistances
            or mechanics.condition_save_advantages
            or mechanics.roll_modifiers
            or mechanics.armor_class_modifier
            or mechanics.speed_modifier_feet
            or selected_damage_reduction_type is not None
        )
        and (
            mechanics.duration_rounds is not None
            or mechanics.concentration
            or mechanics.repeat_save_trigger is not None
        )
    ):
        effects.append(
            EffectResult(
                kind="start_ongoing_effect",
                target_ref=affected_targets[0].target_ref,
                data={
                    "effect_kind": parent_kind,
                    "source_ref": context.source_ref,
                    "source_label": context.creature.name,
                    "definition_id": spell.id,
                    "recast_ends_previous": mechanics.recast_ends_previous,
                    "target_refs": [target.target_ref for target in affected_targets],
                    "duration_rounds": (
                        mechanics.duration_rounds
                        if mechanics.duration_rounds is not None
                        else mechanics.speed_modifier_duration_rounds
                    ),
                    "parameters": {
                        "started_round": context.current_round,
                        "repeat_save_trigger": mechanics.repeat_save_trigger,
                        "save_ability": mechanics.save_ability,
                        "save_dc": context.creature.spellcasting.save_dc,
                        "repeat_failure_conditions": list(
                            mechanics.repeat_failure_conditions
                        ),
                        "repeat_failure_damage": [
                            {
                                "dice": damage.dice,
                                "damage_type": damage.damage_type,
                            }
                            for damage in mechanics.repeat_failure_damage
                        ],
                        "end_events": [list(event) for event in mechanics.end_events],
                        "damage_repeat_save_advantage": (
                            mechanics.damage_repeat_save_advantage
                        ),
                        "maximum_hit_point_modifier": maximum_hit_point_modifier,
                        "also_modify_current_hit_points": (
                            mechanics.also_modify_current_hit_points
                        ),
                        "damage_resistances": list(selected_damage_resistances),
                        "condition_save_advantages": list(
                            mechanics.condition_save_advantages
                        ),
                        "roll_modifiers": [
                            {
                                "roll": modifier.roll,
                                "mode": modifier.mode,
                                "dice": modifier.dice,
                                "value": modifier.value,
                                "subject": modifier.subject,
                            }
                            for modifier in mechanics.roll_modifiers
                        ],
                        "armor_class_modifier": mechanics.armor_class_modifier,
                        "speed_modifier_feet": mechanics.speed_modifier_feet,
                        "damage_reduction_type": selected_damage_reduction_type,
                        "damage_reduction_dice": mechanics.damage_reduction_dice,
                    },
                },
            )
        )
    if selected_conditions:
        for target in affected_targets:
            for condition in selected_conditions:
                condition_data: dict[str, object] = {
                    "condition": condition,
                    "source_ref": context.source_ref,
                    "source_label": context.creature.name,
                    "source_kind": "spell",
                    "definition_id": spell.id,
                }
                if condition in mechanics.self_removal_blocked_conditions:
                    condition_data["metadata"] = {"blocks_self_removal": True}
                if effects:
                    condition_data["parent_effect_kind"] = parent_kind
                if mechanics.expires_on_source_turn_end:
                    condition_data["expires_on_creature_ref"] = context.source_ref
                    condition_data["expires_on_round"] = context.current_round + 1
                effects.append(
                    EffectResult(
                        kind="apply_condition",
                        target_ref=target.target_ref,
                        data=condition_data,
                    )
                )

    removed_conditions: list[str] = []
    if spell.removable_effect_kinds:
        for target in affected_targets:
            selected_removal = context.selected_condition
            if spell.remove_effect_selection == "all" and spell.removable_conditions:
                target_removed_conditions = tuple(
                    condition
                    for condition in spell.removable_conditions
                    if condition in target.target_conditions
                )
                for condition in target_removed_conditions:
                    removed_conditions.append(condition)
                    messages.append(
                        (
                            "system",
                            f"{target.target_label} is no longer {condition}.",
                        )
                    )
                    effects.append(
                        EffectResult(
                            kind="remove_condition",
                            target_ref=target.target_ref,
                            data={"condition": condition},
                        )
                    )
            elif selected_removal in spell.removable_conditions:
                if selected_removal not in target.target_conditions:
                    continue
                removed_conditions.append(selected_removal)
                messages.append(
                    (
                        "system",
                        f"{target.target_label} is no longer {selected_removal}.",
                    )
                )
                effects.append(
                    EffectResult(
                        kind="remove_condition",
                        target_ref=target.target_ref,
                        data={"condition": selected_removal},
                    )
                )
            if "curse" in spell.removable_effect_kinds and (
                spell.remove_effect_selection == "all"
                or (
                    isinstance(selected_removal, str)
                    and selected_removal.startswith("curse@")
                )
            ):
                effect_id = (
                    selected_removal.removeprefix("curse@")
                    if isinstance(selected_removal, str)
                    and selected_removal.startswith("curse@")
                    else None
                )
                effects.append(
                    EffectResult(
                        kind="remove_ongoing_effects",
                        target_ref=target.target_ref,
                        data={
                            "effect_kind": "curse",
                            "effect_id": effect_id,
                            "all": spell.remove_effect_selection == "all",
                        },
                    )
                )
                messages.append(
                    ("system", f"A curse ends on {target.target_label}.")
                )
            if (
                "hit_point_maximum_reduction" in spell.removable_effect_kinds
                and selected_removal == "hit_point_maximum_reduction"
            ):
                effects.append(
                    EffectResult(
                        kind="remove_ongoing_effects",
                        target_ref=target.target_ref,
                        data={
                            "parameter": "negative_maximum_hit_points",
                            "all": True,
                        },
                    )
                )
                messages.append(
                    (
                        "system",
                        f"Hit Point maximum reductions end on {target.target_label}.",
                    )
                )

    return CapabilityActionResult(
        capability_id=spell.id,
        capability_name=spell.name,
        messages=messages,
        effects=effects,
        details={
            "target_ref": context.target.target_ref,
            "target_label": context.target.target_label,
            "target_refs": [target.target_ref for target in targets],
            "target_labels": [target.target_label for target in targets],
            "area": serialize_area(context.area),
            "spell_level": spell.level,
            "slot_level": cast_level,
            "save_detail": save_details[0] if save_details else None,
            "save_details": save_details,
            "attack_roll_detail": attack_details[0] if attack_details else None,
            "attack_roll_details": attack_details,
            "damage_roll_detail": damage_details[0] if damage_details else None,
            "damage_roll_details": damage_details,
            "healing_roll_detail": healing_details[0] if healing_details else None,
            "healing_roll_details": healing_details,
            "temporary_hit_point_detail": (
                temporary_hit_point_details[0]
                if temporary_hit_point_details
                else None
            ),
            "temporary_hit_point_details": temporary_hit_point_details,
            "removed_condition": (
                removed_conditions[0] if removed_conditions else None
            ),
            "success": bool(effects)
            or bool(healing_details)
            or bool(temporary_hit_point_details)
            or any(
                isinstance(detail.get("applied_damage"), int)
                and cast(int, detail["applied_damage"]) > 0
                for detail in damage_details
            ),
        },
    )


def _scale_dice(
    base: str | None,
    increment: str | None,
    levels_above: int,
) -> str | None:
    if base is None or increment is None or levels_above <= 0:
        return base
    base_count, base_sides = _parse_damage_dice(base)
    increment_count, increment_sides = _parse_damage_dice(increment)
    if base_sides != increment_sides:
        raise ValueError("Healing scaling must use the base healing die.")
    return f"{base_count + increment_count * levels_above}d{base_sides}"


def _roll_optional_dice(
    dice: str | None,
    roller: DieRoller,
) -> DicePoolResult | None:
    if dice is None:
        return None
    count, sides = _parse_damage_dice(dice)
    return resolve_dice(count, sides, roller=roller)


def _restoration_detail(
    target: SpellTargetContext,
    *,
    dice: str | None,
    roll: DicePoolResult | None,
    modifier: int,
    total: int,
    applied: int,
) -> dict[str, object]:
    return {
        "target_ref": target.target_ref,
        "target_label": target.target_label,
        "dice": dice,
        "dice_values": [die.result for die in roll.dice] if roll is not None else [],
        "dice_total": roll.subtotal if roll is not None else 0,
        "modifier": modifier,
        "total": total,
        "applied": applied,
    }


def _resolve_follow_up(
    context: SpellActionContext,
    follow_up: FollowUpSpellResolution,
    cast_level: int,
    sequence_step: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if (
        follow_up.target != "area"
        or follow_up.area_radius_feet is None
        or context.area_targets_around is None
        or follow_up.resolution != "saving_throw"
    ):
        return [], []
    assert context.creature.spellcasting is not None
    assert context.roller is not None
    targets = context.area_targets_around(
        context.target.target_ref,
        follow_up.area_radius_feet,
    )
    damage_definitions = follow_up.damage
    if follow_up.slot_damage_increment is not None and cast_level > context.spell.level:
        increment_count, increment_sides = _parse_damage_dice(
            follow_up.slot_damage_increment
        )
        damage_definitions = tuple(
            SpellDamage(
                _scaled_damage_dice(
                    damage.dice,
                    increment_count,
                    increment_sides,
                    cast_level - context.spell.level,
                ),
                damage.damage_type,
            )
            for damage in damage_definitions
        )
    shared_rolls = [
        (
            damage,
            resolve_dice(*_parse_damage_dice(damage.dice), roller=context.roller),
        )
        for damage in damage_definitions
    ]
    save_details: list[dict[str, object]] = []
    damage_details: list[dict[str, object]] = []
    ability = follow_up.save_ability or "dexterity"
    for target in targets:
        save = resolve_saving_throw(
            cast(SavingThrowCreature, target.creature),
            cast(Ability, ability),
            context.creature.spellcasting.save_dc,
            mode=context.save_roll_modes.get(target.target_ref, "normal"),
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
                if save.check.success and follow_up.half_damage_on_save
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


def _scaled_damage_dice(
    dice: str,
    increment_count: int,
    increment_sides: int,
    levels_above: int,
) -> str:
    count, sides = _parse_damage_dice(dice)
    if sides != increment_sides:
        raise ValueError("Slot damage scaling must use the base damage die.")
    return f"{count + increment_count * levels_above}d{sides}"


def _parse_damage_dice(expression: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)d(\d+)", expression)
    if match is None:
        raise ValueError(f"Unsupported damage dice expression: {expression!r}")
    return int(match.group(1)), int(match.group(2))
