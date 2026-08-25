"""Damage rolling, application, and presentation for attacks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ....capabilities import DamageEffect
from ....creatures import Creature
from ....rolls.dice import D20RollMode, DicePoolResult, resolve_dice
from ...models import AttackOutcome, AttackSource


@dataclass(frozen=True)
class AttackDamageResolution:
    """The rolled damage portion of a successful attack."""

    roll: DicePoolResult
    dice: str
    damage: int
    additional_damage: int
    additional_damage_details: tuple[dict[str, object], ...]
    detail: dict[str, object]


def roll_attack_damage(
    attack_source: AttackSource,
    *,
    critical_hit: bool,
    attack_roll_mode: D20RollMode,
    roller: Callable[[int, int], int],
) -> AttackDamageResolution:
    """Roll primary and conditional additional damage in authored order."""
    damage_dice = attack_source.damage_dice
    damage_die_count, damage_die_sides = parse_damage_dice(damage_dice)
    if critical_hit:
        damage_die_count *= 2
        damage_dice = f"{damage_die_count}d{damage_die_sides}"
    damage_roll = resolve_dice(
        damage_die_count,
        damage_die_sides,
        modifier=attack_source.damage_bonus,
        roller=lambda sides: roller(1, sides),
    )
    damage_die_total = damage_roll.subtotal
    damage_total = damage_roll.total
    additional_damage = 0
    additional_damage_details: list[dict[str, object]] = []
    for effect in attack_source.additional_damage:
        if not damage_effect_requirements_met(effect, attack_roll_mode):
            continue
        extra_dice = effect.dice
        extra_bonus = effect.bonus
        extra_type = effect.damage_type
        extra_count, extra_sides = parse_damage_dice(extra_dice)
        if critical_hit:
            extra_count *= 2
            extra_dice = f"{extra_count}d{extra_sides}"
        extra_roll = resolve_dice(
            extra_count,
            extra_sides,
            modifier=extra_bonus,
            roller=lambda sides: roller(1, sides),
        )
        additional_damage += max(0, extra_roll.total)
        additional_damage_details.append(
            {
                "dice": extra_dice,
                "dice_values": [die.result for die in extra_roll.dice],
                "die_rolls": [list(die.rolls) for die in extra_roll.dice],
                "dice_total": extra_roll.subtotal,
                "modifier": extra_bonus,
                "total": extra_roll.total,
                "damage_type": extra_type,
                "critical_hit": critical_hit,
            }
        )
    detail: dict[str, object] = {
        "dice": damage_dice,
        "dice_values": [die.result for die in damage_roll.dice],
        "die_rolls": [list(die.rolls) for die in damage_roll.dice],
        "dice_total": damage_die_total,
        "modifier": attack_source.damage_bonus,
        "total": damage_total,
        "critical_hit": critical_hit,
        "damage_type": attack_source.damage_type,
        "additional_damage": additional_damage_details,
    }
    if attack_source.weapon_id is not None:
        detail["weapon_id"] = attack_source.weapon_id
    if attack_source.weapon_name is not None:
        detail["weapon_name"] = attack_source.weapon_name
    return AttackDamageResolution(
        roll=damage_roll,
        dice=damage_dice,
        damage=max(1, damage_total) + additional_damage,
        additional_damage=additional_damage,
        additional_damage_details=tuple(additional_damage_details),
        detail=detail,
    )


def apply_attack_damage(
    attack: AttackOutcome,
    defender: Creature,
    *,
    attacker_label: str,
    target_label: str,
) -> None:
    """Apply a rolled attack to defenses and append its combat messages."""
    if not attack.hit or attack.damage_roll is None or attack.damage_dice is None:
        return
    damage_total = attack.damage_roll.total
    damage = max(1, damage_total) + attack.additional_damage
    applied_damage = defender.take_damage(max(1, damage_total), attack.damage_type)
    for detail in attack.additional_damage_details:
        extra_damage = detail.get("total", 0)
        extra_type = detail.get("damage_type")
        if isinstance(extra_damage, int):
            applied_damage += defender.take_damage(
                extra_damage,
                extra_type if isinstance(extra_type, str) else None,
            )
    attack.damage = applied_damage
    attack.defender_defeated = defender.get_health() <= 0
    attack.damage_roll_detail = damage_roll_detail(attack, applied_damage)
    attack.messages.extend(
        [
            (
                "system",
                f"Damage to {target_label}: {attack.damage_dice}="
                f"{attack.damage_roll.subtotal} + "
                f"{attack.damage_modifier_label} {attack.damage_modifier} "
                f"= {damage_total}; final damage {damage}, "
                f"applied {applied_damage}.",
            ),
            (
                "system",
                f"{attacker_label} hits {target_label} for {applied_damage} damage.",
            ),
        ]
    )
    if attack.defender_defeated:
        attack.messages.append(("system", f"{target_label} is defeated."))


def damage_roll_detail(
    attack: AttackOutcome,
    applied_damage: int | None = None,
) -> dict[str, object]:
    """Build the stable event payload for an attack's damage roll."""
    assert attack.damage_roll is not None
    detail: dict[str, object] = {
        "dice": attack.damage_dice,
        "dice_values": [die.result for die in attack.damage_roll.dice],
        "die_rolls": [list(die.rolls) for die in attack.damage_roll.dice],
        "dice_total": attack.damage_roll.subtotal,
        "modifier": attack.damage_modifier,
        "total": attack.damage_roll.total,
        "critical_hit": attack.critical_hit,
        "damage_type": attack.damage_type,
        "additional_damage": list(attack.additional_damage_details),
    }
    if applied_damage is not None:
        detail["minimum_applied_total"] = max(1, attack.damage_roll.total)
        detail["applied_damage"] = applied_damage
    if attack.weapon_id is not None:
        detail["weapon_id"] = attack.weapon_id
    if attack.weapon_name is not None:
        detail["weapon_name"] = attack.weapon_name
    return detail


def damage_effect_requirements_met(
    effect: DamageEffect,
    roll_mode: D20RollMode,
) -> bool:
    """Return whether conditional damage matches the resolved attack mode."""
    return all(requirement.mode == roll_mode for requirement in effect.requirements)


def parse_damage_dice(damage: str) -> tuple[int, int]:
    """Parse a simple NdS damage expression."""
    count_text, sides_text = damage.lower().split("d", 1)
    return int(count_text), int(sides_text)
