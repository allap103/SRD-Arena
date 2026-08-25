"""Attack-roll resolution and position-derived roll modes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ...creatures import Creature
from ...geometry import Position
from ...rolls.dice import (
    CheckResult,
    D20RollMode,
    D20RollResult,
    combine_roll_modes,
    resolve_check,
    resolve_d20,
)
from ..behaviors import is_adjacent
from ..models import AttackSource


@dataclass(frozen=True)
class AttackRollResolution:
    """The complete result of the to-hit portion of an attack."""

    result: D20RollResult
    check: CheckResult
    attack_type: str
    attack_modifier: int
    sourced_modifier: int
    target_ac: int
    hit: bool
    critical_hit: bool
    detail: dict[str, object]


def resolve_attack_roll(
    attacker: Creature,
    defender: Creature,
    attack_source: AttackSource,
    *,
    attacker_position: Position | None,
    nearby_opponent_positions: tuple[Position, ...],
    attack_roll_mode_override: D20RollMode | None,
    roller: Callable[[int], int],
    automatic_critical_provider_ids: tuple[str, ...],
) -> AttackRollResolution:
    """Resolve hit, critical, and presentation data for an attack roll."""
    attack_type = attack_source.attack_modes[0]
    sourced_modifier = attacker.resolve_roll_modifiers("attack_roll", roller)
    attack_modifier = attack_source.attack_bonus + sourced_modifier
    roll_mode = combine_roll_modes(
        attack_roll_mode_override
        or attack_roll_mode(
            attack_type,
            attacker_position,
            nearby_opponent_positions,
        ),
        attacker.roll_mode("attack_roll"),
    )
    attack_result = resolve_d20(
        modifier=attack_modifier,
        mode=roll_mode,
        roller=roller,
    )
    target_ac = defender.get_armor_class()
    attack_check = resolve_check(attack_result, target_ac)
    critical_miss = attack_result.selected == 1
    natural_critical_hit = attack_result.selected == 20
    hit = not critical_miss and (natural_critical_hit or attack_check.success)
    critical_hit = hit and (
        natural_critical_hit or bool(automatic_critical_provider_ids)
    )
    detail: dict[str, object] = {
        "die": attack_result.selected,
        "dice": list(attack_result.dice),
        "selected_index": attack_result.selected_index,
        "mode": attack_result.mode,
        "attack_type": attack_type,
        "ability_modifier": attack_source.ability_modifier,
        "proficiency_bonus": attack_source.proficiency_bonus,
        "modifier": attack_modifier,
        "sourced_modifier": sourced_modifier,
        "total": attack_result.total,
        "target_ac": target_ac,
        "critical_miss": critical_miss,
        "critical_hit": critical_hit,
        "automatic_critical_provider_ids": list(automatic_critical_provider_ids),
    }
    if attack_source.weapon_id is not None:
        detail["weapon_id"] = attack_source.weapon_id
    if attack_source.weapon_name is not None:
        detail["weapon_name"] = attack_source.weapon_name
    return AttackRollResolution(
        result=attack_result,
        check=attack_check,
        attack_type=attack_type,
        attack_modifier=attack_modifier,
        sourced_modifier=sourced_modifier,
        target_ac=target_ac,
        hit=hit,
        critical_hit=critical_hit,
        detail=detail,
    )


def attack_roll_mode(
    attack_type: str,
    attacker_position: Position | None,
    nearby_opponent_positions: tuple[Position, ...],
) -> D20RollMode:
    """Return disadvantage for a ranged attack made beside an opponent."""
    if attack_type != "ranged" or attacker_position is None:
        return "normal"
    if any(
        is_adjacent(attacker_position, position)
        for position in nearby_opponent_positions
    ):
        return "disadvantage"
    return "normal"
