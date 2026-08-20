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
from .definitions import Spell, SpellDamage

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
    attack_roll_modes: dict[str, D20RollMode] = field(default_factory=dict)
    automatic_critical_providers: dict[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    cast_level: int | None = None
    save_roll_modes: dict[str, D20RollMode] = field(default_factory=dict)


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

    save_details: list[dict[str, object]] = []
    attack_details: list[dict[str, object]] = []
    damage_details: list[dict[str, object]] = []
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
            applied = target.creature.take_damage(final_damage)
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
        outcome = (
            "damages"
            if target_damage > 0
            else "affects"
            if affected and mechanics.conditions
            else "does not affect"
        )
        if not spell.removable_conditions:
            messages.append(
                ("system", f"{spell.name} {outcome} {target.target_label}.")
            )

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
    if (
        affected_targets
        and mechanics.conditions
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
                    "target_refs": [target.target_ref for target in affected_targets],
                    "duration_rounds": mechanics.duration_rounds,
                    "parameters": {
                        "started_round": context.current_round,
                        "repeat_save_trigger": mechanics.repeat_save_trigger,
                        "save_ability": mechanics.save_ability,
                        "save_dc": context.creature.spellcasting.save_dc,
                        "repeat_failure_conditions": list(
                            mechanics.repeat_failure_conditions
                        ),
                        "end_events": [list(event) for event in mechanics.end_events],
                        "damage_repeat_save_advantage": (
                            mechanics.damage_repeat_save_advantage
                        ),
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
    if spell.removable_conditions:
        for target in affected_targets:
            removed_condition = context.selected_condition
            if (
                removed_condition not in spell.removable_conditions
                or removed_condition not in target.target_conditions
            ):
                messages.append(
                    (
                        "system",
                        f"No removable condition on "
                        f"{target.target_label.lower()} is affected.",
                    )
                )
                continue
            removed_conditions.append(removed_condition)
            messages.append(
                (
                    "system",
                    f"{target.target_label} is no longer {removed_condition}.",
                )
            )
            effects.append(
                EffectResult(
                    kind="remove_condition",
                    target_ref=target.target_ref,
                    data={"condition": removed_condition},
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
            "removed_condition": (
                removed_conditions[0] if removed_conditions else None
            ),
            "success": bool(effects)
            or any(
                isinstance(detail.get("applied_damage"), int)
                and cast(int, detail["applied_damage"]) > 0
                for detail in damage_details
            ),
        },
    )


def _parse_damage_dice(expression: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)d(\d+)", expression)
    if match is None:
        raise ValueError(f"Unsupported damage dice expression: {expression!r}")
    return int(match.group(1)), int(match.group(2))
