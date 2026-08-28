"""Select and describe the attack a creature is invoking."""

from __future__ import annotations

from ....capabilities import DamageEffect
from ....creatures import Creature
from ....creatures.stat_block_actions import AttackActionDefinition
from ....equipment import Item
from ....geometry import Grid
from ...models import AttackSource


def equipped_weapon(attacker: Creature, items_by_id: dict[str, Item]) -> Item | None:
    """Return the first equipped item that defines a weapon attack.

    >>> from types import SimpleNamespace
    >>> from ....equipment import WeaponStat
    >>> sword = Item(
    ...     "sword", "Sword", "", "weapon",
    ...     weapon_stat=WeaponStat([], "1d8", "slashing", []),
    ... )
    >>> attacker = SimpleNamespace(
    ...     equipment=SimpleNamespace(
    ...         equipped_items={"right_hand": "sword", "left_hand": None}
    ...     )
    ... )
    >>> equipped_weapon(attacker, {"sword": sword}) is sword
    True
    """
    for slot in ("right_hand", "left_hand"):
        item_id = attacker.equipment.equipped_items.get(slot)
        if item_id is None:
            continue
        item = items_by_id.get(item_id)
        if item is not None and item.weapon_stat is not None:
            return item
    return None


def has_free_hand(creature: Creature) -> bool:
    """Return whether either hand equipment slot is empty.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     equipment=SimpleNamespace(
    ...         equipped_items={"right_hand": "sword", "left_hand": None}
    ...     )
    ... )
    >>> has_free_hand(creature)
    True
    """
    return any(
        creature.equipment.equipped_items.get(slot) is None
        for slot in ("right_hand", "left_hand")
    )


def unarmed_attack_source(attacker: Creature) -> AttackSource:
    """Build the fallback unarmed attack source for a creature.

    >>> from types import SimpleNamespace
    >>> attacker = SimpleNamespace(
    ...     attributes=SimpleNamespace(strength=14),
    ...     get_modifier=lambda score: (score - 10) // 2,
    ... )
    >>> source = unarmed_attack_source(attacker)
    >>> (source.name, source.attack_bonus, source.damage_bonus)
    ('Unarmed Strike', 2, 2)
    """
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
    """Build an attack source from an equipped weapon and creature stats.

    >>> from types import SimpleNamespace
    >>> from ....equipment import WeaponStat
    >>> bow = Item(
    ...     "shortbow", "Shortbow", "", "weapon",
    ...     weapon_stat=WeaponStat(
    ...         [], "1d6", "piercing", [], "ranged", 80, 320, "martial"
    ...     ),
    ... )
    >>> attacker = SimpleNamespace(
    ...     attributes=SimpleNamespace(
    ...         strength=10, dexterity=16, proficiency_bonus=2,
    ...         proficiencies={"weapons": ["martial"]},
    ...     ),
    ...     get_modifier=lambda score: (score - 10) // 2,
    ... )
    >>> source = weapon_attack_source(attacker, bow)
    >>> (source.attack_bonus, source.damage_bonus, source.attack_modes)
    (5, 3, ('ranged',))
    """
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
    """Build an attack source from an authored monster attack.

    >>> from ....capabilities import CapabilityTarget
    >>> attack = AttackActionDefinition(
    ...     "Bite", ("melee",), 5, CapabilityTarget("creature"),
    ...     5, None, None, (DamageEffect("1d8", 3, "piercing"),),
    ... )
    >>> source = stat_block_attack_source(attack)
    >>> (source.name, source.damage_dice, source.reach_feet)
    ('Bite', '1d8', 5)
    """
    damage = [effect for effect in attack.hit if isinstance(effect, DamageEffect)]
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


def select_attack_source(
    attacker: Creature,
    items_by_id: dict[str, Item],
    *,
    preferred_attack_type: str | None = None,
    preferred_attack_name: str | None = None,
) -> AttackSource | None:
    """Select the requested attack source and lock it to one attack mode.

    >>> from types import SimpleNamespace
    >>> attacker = SimpleNamespace(
    ...     equipment=SimpleNamespace(
    ...         equipped_items={"right_hand": None, "left_hand": None}
    ...     ),
    ...     stat_block_actions={},
    ... )
    >>> select_attack_source(attacker, {}) is None
    True
    """
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


def attack_sources(
    attacker: Creature,
    items_by_id: dict[str, Item],
) -> list[AttackSource]:
    """Return the weapon or authored attacks available to a creature.

    >>> from types import SimpleNamespace
    >>> attacker = SimpleNamespace(
    ...     equipment=SimpleNamespace(
    ...         equipped_items={"right_hand": None, "left_hand": None}
    ...     ),
    ...     stat_block_actions={},
    ... )
    >>> attack_sources(attacker, {})
    []
    """
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
    grid: Grid,
    *,
    preferred_attack_type: str | None = None,
    preferred_attack_name: str | None = None,
) -> int:
    """Return the selected attack's normal reach or range in grid squares.

    >>> from types import SimpleNamespace
    >>> attacker = SimpleNamespace(
    ...     equipment=SimpleNamespace(
    ...         equipped_items={"right_hand": None, "left_hand": None}
    ...     ),
    ...     stat_block_actions={},
    ... )
    >>> attack_range_squares(attacker, {}, Grid(10, 10))
    1
    """
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
        source.range_normal or 5 if attack_type == "ranged" else source.reach_feet or 5
    )
    return int(grid.distance_from_feet(range_feet, minimum=1))


def source_for_mode(source: AttackSource, attack_type: str) -> AttackSource:
    """Copy an attack source with one selected attack mode.

    >>> source = AttackSource(
    ...     "Spear", "1d6", 2, "STR mod", "piercing", 4,
    ...     "STR mod + proficiency", ("melee", "ranged"),
    ... )
    >>> source_for_mode(source, "ranged").attack_modes
    ('ranged',)
    """
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


def selected_attack_type(
    attacker: Creature,
    items_by_id: dict[str, Item],
    *,
    preferred_attack_type: str | None = None,
) -> str:
    """Return the selected source's attack mode, with a melee fallback.

    >>> from types import SimpleNamespace
    >>> attacker = SimpleNamespace(
    ...     equipment=SimpleNamespace(
    ...         equipped_items={"right_hand": None, "left_hand": None}
    ...     ),
    ...     stat_block_actions={},
    ... )
    >>> selected_attack_type(attacker, {}, preferred_attack_type="ranged")
    'ranged'
    """
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
    """Return whether the creature has a selectable melee attack.

    >>> from types import SimpleNamespace
    >>> attacker = SimpleNamespace(
    ...     equipment=SimpleNamespace(
    ...         equipped_items={"right_hand": None, "left_hand": None}
    ...     ),
    ...     stat_block_actions={},
    ... )
    >>> can_make_opportunity_attack(attacker, {})
    False
    """
    attack_source = select_attack_source(
        attacker,
        items_by_id,
        preferred_attack_type="melee",
    )
    return attack_source is not None and "melee" in attack_source.attack_modes


def weapon_proficiency_bonus(attacker: Creature, weapon: Item | None) -> int:
    """Return the proficiency bonus contributed by an equipped weapon.

    >>> from types import SimpleNamespace
    >>> from ....equipment import WeaponStat
    >>> sword = Item(
    ...     "longsword", "Longsword", "", "weapon",
    ...     weapon_stat=WeaponStat(
    ...         [], "1d8", "slashing", [], weapon_category="martial"
    ...     ),
    ... )
    >>> attacker = SimpleNamespace(
    ...     attributes=SimpleNamespace(
    ...         proficiency_bonus=3, proficiencies={"weapons": ["martial"]}
    ...     )
    ... )
    >>> weapon_proficiency_bonus(attacker, sword)
    3
    """
    if weapon is None or weapon.weapon_stat is None:
        return 0
    weapon_proficiencies = attacker.attributes.proficiencies.get("weapons", [])
    if not isinstance(weapon_proficiencies, list):
        return 0
    category = weapon.weapon_stat.weapon_category
    is_proficient = (
        weapon.id in weapon_proficiencies
        or weapon.name.casefold()
        in {str(item).casefold() for item in weapon_proficiencies}
        or category in weapon_proficiencies
    )
    return attacker.attributes.proficiency_bonus if is_proficient else 0
