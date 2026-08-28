"""Stable facade and high-level coordinator for attack resolution.

Source selection, attack rolls, damage, and triggered-effect matching live in
the focused ``attack_runtime`` package. Callers import this facade so the
readable attack pipeline can evolve without exposing those boundaries.
"""

from __future__ import annotations

from collections.abc import Callable

from ...creatures import Creature
from ...equipment import Item
from ...geometry import Position
from ...rolls.dice import D20RollMode, roll_dice, roll_die
from ..encounter_models.resolution import AttackOutcome
from .attack_runtime.damage import (
    apply_attack_damage,
    damage_roll_detail,
    parse_damage_dice,
    roll_attack_damage,
)
from .attack_runtime.rolls import attack_roll_mode, resolve_attack_roll
from .attack_runtime.sources import (
    attack_range_squares,
    attack_sources,
    can_make_opportunity_attack,
    equipped_weapon,
    has_free_hand,
    select_attack_source,
    selected_attack_type,
    source_for_mode,
    stat_block_attack_source,
    unarmed_attack_source,
    weapon_attack_source,
    weapon_proficiency_bonus,
)
from .attack_runtime.triggers import matching_damage_reroll_rule

__all__ = [
    "apply_attack_damage",
    "attack_range_squares",
    "attack_roll_mode",
    "attack_sources",
    "can_make_opportunity_attack",
    "damage_roll_detail",
    "equipped_weapon",
    "has_free_hand",
    "matching_damage_reroll_rule",
    "parse_damage_dice",
    "resolve_attack",
    "select_attack_source",
    "selected_attack_type",
    "source_for_mode",
    "stat_block_attack_source",
    "unarmed_attack_source",
    "weapon_attack_source",
    "weapon_proficiency_bonus",
]


def resolve_attack(
    attacker: Creature,
    defender: Creature,
    attacker_label: str,
    target_label: str,
    action_label: str = "Attack",
    items_by_id: dict[str, Item] | None = None,
    attacker_position: Position | None = None,
    nearby_opponent_positions: tuple[Position, ...] = (),
    preferred_attack_type: str | None = None,
    preferred_attack_name: str | None = None,
    attack_roll_mode_override: D20RollMode | None = None,
    sourced_attack_modifier: int | None = None,
    sourced_attack_roll_mode: D20RollMode | None = None,
    target_armor_class: int | None = None,
    sourced_damage_modifier_for: Callable[[], int] | None = None,
    d20_roller: Callable[[int], int] = roll_die,
    dice_roller: Callable[[int, int], int] = roll_dice,
    automatic_critical_provider_ids: tuple[str, ...] = (),
) -> AttackOutcome:
    """Resolve attack selection, hit determination, and rolled damage.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> from srd_arena.domain.encounters.encounter_models.resolution import AttackSource
    >>> source = AttackSource(
    ...     "Claw", "1d6", 2, "STR mod", "slashing", 5,
    ...     "attack bonus", ("melee",),
    ... )
    >>> attacker = SimpleNamespace(
    ...     resolve_roll_modifiers=lambda *args: 0,
    ...     roll_mode=lambda *args: "normal",
    ... )
    >>> defender = SimpleNamespace(get_armor_class=lambda: 15)
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.attack_resolution."
    ...     "select_attack_source",
    ...     return_value=source,
    ... ):
    ...     outcome = resolve_attack(
    ...         attacker, defender, "Wolf", "Hero",
    ...         d20_roller=lambda sides: 12,
    ...         dice_roller=lambda count, sides: 4,
    ...     )
    >>> (outcome.hit, outcome.attack_roll, outcome.damage)
    (True, 17, 6)
    """
    attack_source = select_attack_source(
        attacker,
        items_by_id or {},
        preferred_attack_type=preferred_attack_type,
        preferred_attack_name=preferred_attack_name,
    )
    if attack_source is None:
        attack_source = unarmed_attack_source(attacker)

    attack_roll = resolve_attack_roll(
        attacker,
        defender,
        attack_source,
        attacker_position=attacker_position,
        nearby_opponent_positions=nearby_opponent_positions,
        attack_roll_mode_override=attack_roll_mode_override,
        sourced_modifier_override=sourced_attack_modifier,
        sourced_roll_mode_override=sourced_attack_roll_mode,
        target_armor_class=target_armor_class,
        roller=d20_roller,
        automatic_critical_provider_ids=automatic_critical_provider_ids,
    )
    action_prefix = action_label if action_label != "Attack" else "Attack"
    attack_detail_message = (
        f"{action_prefix}: {attacker_label} attacks {target_label}. "
        f"Roll d20={attack_roll.result.selected} + "
        f"{attack_source.attack_bonus_label} {attack_roll.attack_modifier} "
        f"= {attack_roll.result.total} vs {target_label} AC {attack_roll.target_ac}."
    )
    if not attack_roll.hit:
        return AttackOutcome(
            messages=[
                ("system", attack_detail_message),
                ("system", f"{attacker_label} misses {target_label}."),
            ],
            hit=False,
            attack_roll=attack_roll.result.total,
            damage=0,
            defender_defeated=False,
            attack_roll_detail=attack_roll.detail,
            attack_check=attack_roll.check,
            attack_type=attack_roll.attack_type,
            critical_hit=attack_roll.critical_hit,
        )

    damage_modifier_for = sourced_damage_modifier_for or (
        lambda: attacker.resolve_roll_modifiers(
            "damage_roll",
            lambda sides: dice_roller(1, sides),
        )
    )
    damage = roll_attack_damage(
        attack_source,
        critical_hit=attack_roll.critical_hit,
        attack_roll_mode=attack_roll.result.mode,
        roller=dice_roller,
        sourced_modifier_for=damage_modifier_for,
    )
    messages = [("system", attack_detail_message)]
    if attack_roll.critical_hit:
        messages.append(("system", f"Critical hit by {attacker_label}!"))
    return AttackOutcome(
        messages=messages,
        hit=True,
        attack_roll=attack_roll.result.total,
        damage=damage.damage,
        defender_defeated=False,
        attack_roll_detail=attack_roll.detail,
        damage_roll_detail=damage.detail,
        attack_check=attack_roll.check,
        damage_roll=damage.roll,
        damage_dice=damage.dice,
        damage_modifier=damage.roll.modifier,
        sourced_damage_modifier=damage.sourced_modifier,
        damage_modifier_label=attack_source.damage_bonus_label,
        attack_type=attack_roll.attack_type,
        damage_type=attack_source.damage_type,
        critical_hit=attack_roll.critical_hit,
        weapon_id=attack_source.weapon_id,
        weapon_name=attack_source.weapon_name,
        weapon_properties=attack_source.weapon_properties,
        additional_damage=damage.additional_damage,
        additional_damage_details=damage.additional_damage_details,
        hit_effects=attack_source.hit_effects,
    )
