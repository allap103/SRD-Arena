from __future__ import annotations

from ...creatures import Creature
from ...creatures.stat_block_actions import (
    AttackActionDefinition,
    DamageEffect,
)
from ...equipment import Item
from ...geometry import Position
from ...rolls.dice import (
    D20RollMode,
    resolve_check,
    resolve_d20,
    resolve_dice,
    roll_dice,
    roll_die,
)
from ...effects.triggered import (
    TriggeredEffect,
    matching_effects,
    reroll_eligible_indices,
)
from ..behaviors import is_adjacent as _is_adjacent
from ..models import AttackOutcome, AttackSource


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
    d20_roller=roll_die,
    dice_roller=roll_dice,
    automatic_critical_provider_ids: tuple[str, ...] = (),
) -> AttackOutcome:
    attack_source = select_attack_source(
        attacker,
        items_by_id or {},
        preferred_attack_type=preferred_attack_type,
        preferred_attack_name=preferred_attack_name,
    )
    if attack_source is None:
        attack_source = unarmed_attack_source(attacker)
    attack_type = attack_source.attack_modes[0]
    attack_modifier = attack_source.attack_bonus
    roll_mode = attack_roll_mode_override or attack_roll_mode(
        attack_type,
        attacker_position,
        nearby_opponent_positions,
    )
    attack_result = resolve_d20(
        modifier=attack_modifier,
        mode=roll_mode,
        roller=d20_roller,
    )
    target_ac = defender.get_armor_class()
    attack_check = resolve_check(attack_result, target_ac)
    critical_miss = attack_result.selected == 1
    natural_critical_hit = attack_result.selected == 20
    hit = not critical_miss and (natural_critical_hit or attack_check.success)
    critical_hit = hit and (
        natural_critical_hit or bool(automatic_critical_provider_ids)
    )
    attack_roll_detail = {
        "die": attack_result.selected,
        "dice": list(attack_result.dice),
        "selected_index": attack_result.selected_index,
        "mode": attack_result.mode,
        "attack_type": attack_type,
        "ability_modifier": attack_source.ability_modifier,
        "proficiency_bonus": attack_source.proficiency_bonus,
        "modifier": attack_modifier,
        "total": attack_result.total,
        "target_ac": target_ac,
        "critical_miss": critical_miss,
        "critical_hit": critical_hit,
        "automatic_critical_provider_ids": list(
            automatic_critical_provider_ids
        ),
    }
    if attack_source.weapon_id is not None:
        attack_roll_detail["weapon_id"] = attack_source.weapon_id
    if attack_source.weapon_name is not None:
        attack_roll_detail["weapon_name"] = attack_source.weapon_name
    action_prefix = action_label if action_label != "Attack" else "Attack"
    attack_detail_message = (
        f"{action_prefix}: {attacker_label} attacks {target_label}. "
        f"Roll d20={attack_result.selected} + {attack_source.attack_bonus_label} {attack_modifier} "
        f"= {attack_result.total} vs {target_label} AC {target_ac}."
    )
    if not hit:
        return AttackOutcome(
            messages=[
                ("system", attack_detail_message),
                ("system", f"{attacker_label} misses {target_label}."),
            ],
            hit=False,
            attack_roll=attack_result.total,
            damage=0,
            defender_defeated=False,
            attack_roll_detail=attack_roll_detail,
            attack_check=attack_check,
            attack_type=attack_type,
            critical_hit=critical_hit,
        )

    damage_dice = attack_source.damage_dice
    damage_die_count, damage_die_sides = parse_damage_dice(damage_dice)
    if critical_hit:
        damage_die_count *= 2
        damage_dice = f"{damage_die_count}d{damage_die_sides}"
    damage_roll = resolve_dice(
        damage_die_count,
        damage_die_sides,
        modifier=attack_source.damage_bonus,
        roller=lambda sides: dice_roller(1, sides),
    )
    damage_die_total = damage_roll.subtotal
    damage_total = damage_roll.total
    additional_damage = 0
    additional_damage_details: list[dict[str, object]] = []
    for effect in attack_source.additional_damage:
        if not _damage_effect_requirements_met(effect, attack_result.mode):
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
            roller=lambda sides: dice_roller(1, sides),
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
    damage_roll_detail = {
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
        damage_roll_detail["weapon_id"] = attack_source.weapon_id
    if attack_source.weapon_name is not None:
        damage_roll_detail["weapon_name"] = attack_source.weapon_name
    messages = [("system", attack_detail_message)]
    if critical_hit:
        messages.append(("system", f"Critical hit by {attacker_label}!"))
    return AttackOutcome(
        messages=messages,
        hit=True,
        attack_roll=attack_result.total,
        damage=max(1, damage_total) + additional_damage,
        defender_defeated=False,
        attack_roll_detail=attack_roll_detail,
        damage_roll_detail=damage_roll_detail,
        attack_check=attack_check,
        damage_roll=damage_roll,
        damage_dice=damage_dice,
        damage_modifier=attack_source.damage_bonus,
        damage_modifier_label=attack_source.damage_bonus_label,
        attack_type=attack_type,
        damage_type=attack_source.damage_type,
        critical_hit=critical_hit,
        weapon_id=attack_source.weapon_id,
        weapon_name=attack_source.weapon_name,
        weapon_properties=attack_source.weapon_properties,
        additional_damage=additional_damage,
        additional_damage_details=tuple(additional_damage_details),
        hit_effects=attack_source.hit_effects,
    )


def apply_attack_damage(
    attack: AttackOutcome,
    defender: Creature,
    *,
    attacker_label: str,
    target_label: str,
) -> None:
    if not attack.hit or attack.damage_roll is None or attack.damage_dice is None:
        return
    damage_total = attack.damage_roll.total
    damage = max(1, damage_total) + attack.additional_damage
    applied_damage = defender.take_damage(damage)
    attack.damage = applied_damage
    attack.defender_defeated = defender.get_health() <= 0
    attack.damage_roll_detail = damage_roll_detail(attack, applied_damage)
    attack.messages.extend(
        [
            (
                "system",
                f"Damage to {target_label}: {attack.damage_dice}="
                f"{attack.damage_roll.subtotal} + {attack.damage_modifier_label} {attack.damage_modifier} "
                f"= {damage_total}; final damage {damage}, applied {applied_damage}.",
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


def equipped_weapon(attacker: Creature, items_by_id: dict[str, Item]) -> Item | None:
    for slot in ("right_hand", "left_hand"):
        item_id = attacker.equipment.equipped_items.get(slot)
        if item_id is None:
            continue
        item = items_by_id.get(item_id)
        if item is not None and item.weapon_stat is not None:
            return item
    return None


def has_free_hand(creature: Creature) -> bool:
    return any(
        creature.equipment.equipped_items.get(slot) is None
        for slot in ("right_hand", "left_hand")
    )


def unarmed_attack_source(attacker: Creature) -> AttackSource:
    strength_modifier = attacker.get_modifier(attacker.attributes.strength)
    return AttackSource(
        name="Unarmed Strike",
        damage_dice="1d4",
        damage_bonus=strength_modifier,
        damage_bonus_label="STR mod",
        damage_type="damage",
        attack_bonus=strength_modifier,
        attack_bonus_label="STR mod",
        ability_modifier=strength_modifier,
        attack_modes=("melee",),
    )


def weapon_attack_source(attacker: Creature, weapon: Item) -> AttackSource:
    assert weapon.weapon_stat is not None
    attack_type = weapon.weapon_stat.attack_type or "melee"
    ability_modifier = (
        attacker.get_modifier(attacker.attributes.dexterity)
        if attack_type == "ranged"
        else attacker.get_modifier(attacker.attributes.strength)
    )
    proficiency_bonus = weapon_proficiency_bonus(attacker, weapon)
    ability_label = "DEX mod" if attack_type == "ranged" else "STR mod"
    return AttackSource(
        name=weapon.name,
        damage_dice=weapon.weapon_stat.damage,
        damage_bonus=ability_modifier,
        damage_bonus_label=ability_label,
        damage_type=weapon.weapon_stat.damage_type,
        attack_bonus=ability_modifier + proficiency_bonus,
        attack_bonus_label=(
            f"{ability_label} + proficiency {proficiency_bonus}"
            if proficiency_bonus
            else ability_label
        ),
        ability_modifier=ability_modifier,
        proficiency_bonus=proficiency_bonus,
        attack_modes=(attack_type,),
        range_normal=weapon.weapon_stat.range_normal,
        range_long=weapon.weapon_stat.range_long,
        weapon_id=weapon.id,
        weapon_name=weapon.name,
        weapon_properties=tuple(weapon.weapon_stat.properties),
    )


def stat_block_attack_source(attack: AttackActionDefinition) -> AttackSource:
    damage = [
        effect for effect in attack.hit if isinstance(effect, DamageEffect)
    ]
    if not damage:
        raise ValueError(f"Attack '{attack.name}' has no damage effect.")
    primary, *additional = damage
    return AttackSource(
        name=attack.name,
        damage_dice=primary.dice,
        damage_bonus=primary.bonus,
        damage_bonus_label="bonus",
        damage_type=primary.damage_type,
        attack_bonus=attack.attack_bonus,
        attack_bonus_label="attack bonus",
        attack_modes=attack.attack_modes,
        range_normal=attack.range_normal_feet,
        range_long=attack.range_long_feet,
        weapon_name=attack.name,
        additional_damage=tuple(additional),
        hit_effects=tuple(
            effect for effect in attack.hit if not isinstance(effect, DamageEffect)
        ),
        reach_feet=attack.reach_feet,
    )


def _damage_effect_requirements_met(
    effect: DamageEffect,
    roll_mode: D20RollMode,
) -> bool:
    return all(
        requirement.mode == roll_mode
        for requirement in effect.requirements
    )


def select_attack_source(
    attacker: Creature,
    items_by_id: dict[str, Item],
    *,
    preferred_attack_type: str | None = None,
    preferred_attack_name: str | None = None,
) -> AttackSource | None:
    sources = attack_sources(attacker, items_by_id)
    if not sources:
        return None
    if preferred_attack_name is not None:
        for source in sources:
            if source.name != preferred_attack_name:
                continue
            if (
                preferred_attack_type is not None
                and preferred_attack_type not in source.attack_modes
            ):
                return None
            return source_for_mode(
                source,
                preferred_attack_type or source.attack_modes[0],
            )
        return None
    if preferred_attack_type is not None:
        for source in sources:
            if preferred_attack_type not in source.attack_modes:
                continue
            return source_for_mode(source, preferred_attack_type)
        return None

    for attack_type_name in ("melee", "ranged"):
        for source in sources:
            if attack_type_name not in source.attack_modes:
                continue
            return source_for_mode(source, attack_type_name)
    return None


def attack_sources(attacker: Creature, items_by_id: dict[str, Item]) -> list[AttackSource]:
    weapon = equipped_weapon(attacker, items_by_id)
    if weapon is not None:
        return [weapon_attack_source(attacker, weapon)]
    return [
        stat_block_attack_source(action)
        for action in attacker.stat_block_actions.values()
        if isinstance(action, AttackActionDefinition)
    ]


def attack_range_squares(
    attacker: Creature,
    items_by_id: dict[str, Item],
    *,
    preferred_attack_type: str | None = None,
    preferred_attack_name: str | None = None,
) -> int:
    source = select_attack_source(
        attacker,
        items_by_id,
        preferred_attack_type=preferred_attack_type,
        preferred_attack_name=preferred_attack_name,
    )
    if source is None:
        return 1
    attack_type = source.attack_modes[0]
    range_feet = (
        source.range_normal or 5
        if attack_type == "ranged"
        else source.reach_feet or 5
    )
    return max(1, range_feet // attacker.attributes.movement.feet_per_square)

def source_for_mode(source: AttackSource, attack_type: str) -> AttackSource:
    return AttackSource(
        name=source.name,
        damage_dice=source.damage_dice,
        damage_bonus=source.damage_bonus,
        damage_bonus_label=source.damage_bonus_label,
        damage_type=source.damage_type,
        attack_bonus=source.attack_bonus,
        attack_bonus_label=source.attack_bonus_label,
        ability_modifier=source.ability_modifier,
        proficiency_bonus=source.proficiency_bonus,
        attack_modes=(attack_type,),
        range_normal=source.range_normal,
        range_long=source.range_long,
        weapon_id=source.weapon_id,
        weapon_name=source.weapon_name,
        weapon_properties=source.weapon_properties,
        additional_damage=source.additional_damage,
        hit_effects=source.hit_effects,
        reach_feet=source.reach_feet,
    )


def attack_roll_mode(
    attack_type: str,
    attacker_position: Position | None,
    nearby_opponent_positions: tuple[Position, ...],
) -> D20RollMode:
    if attack_type != "ranged" or attacker_position is None:
        return "normal"
    if any(_is_adjacent(attacker_position, position) for position in nearby_opponent_positions):
        return "disadvantage"
    return "normal"


def selected_attack_type(
    attacker: Creature,
    items_by_id: dict[str, Item],
    *,
    preferred_attack_type: str | None = None,
) -> str:
    attack_source = select_attack_source(
        attacker,
        items_by_id,
        preferred_attack_type=preferred_attack_type,
    )
    if attack_source is None:
        return preferred_attack_type or "melee"
    return attack_source.attack_modes[0]


def can_make_opportunity_attack(
    attacker: Creature,
    items_by_id: dict[str, Item],
) -> bool:
    attack_source = select_attack_source(attacker, items_by_id, preferred_attack_type="melee")
    return attack_source is not None and "melee" in attack_source.attack_modes


def matching_damage_reroll_rule(
    attacker: Creature,
    attack: AttackOutcome,
) -> TriggeredEffect | None:
    if attack.damage_roll is None:
        return None
    wielded_with = (
        "two_hands"
        if "two-handed" in attack.weapon_properties
        else "one_hand"
    )
    context = {
        "attack_type": attack.attack_type,
        "wielded_with": wielded_with,
        "weapon_properties": list(attack.weapon_properties),
    }
    return next(
        (
            effect
            for effect in matching_effects(
                attacker.triggered_effects,
                "weapon_damage_rolled",
                context,
            )
            if reroll_eligible_indices(effect, attack.damage_roll)
        ),
        None,
    )


def weapon_proficiency_bonus(attacker: Creature, weapon: Item | None) -> int:
    if weapon is None or weapon.weapon_stat is None:
        return 0
    weapon_proficiencies = attacker.attributes.proficiencies.get("weapons", [])
    if not isinstance(weapon_proficiencies, list):
        return 0
    category = weapon.weapon_stat.weapon_category
    is_proficient = (
        weapon.id in weapon_proficiencies
        or weapon.name.casefold() in {str(item).casefold() for item in weapon_proficiencies}
        or category in weapon_proficiencies
    )
    return attacker.attributes.proficiency_bonus if is_proficient else 0


def parse_damage_dice(damage: str) -> tuple[int, int]:
    count_text, sides_text = damage.lower().split("d", 1)
    return int(count_text), int(sides_text)
