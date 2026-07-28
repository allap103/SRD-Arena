import re

from srd_arena.content.schemas.bestiary import (
    BestiaryActionSchema,
    BestiaryMonsterSchema,
)
from srd_arena.content.schemas.action_mechanics import (
    AttackActionMechanicsSchema,
    DamageEffectSchema,
)
from srd_arena.domain.creatures.monster_attack import (
    MonsterAttack,
    MonsterAttackDamage,
)
from srd_arena.domain.creatures.stat_block_actions import ActionEffect


def build_monster_attacks(
    stat_block: BestiaryMonsterSchema | None,
) -> list[MonsterAttack]:
    if stat_block is None:
        return []
    attacks: list[MonsterAttack] = []
    for action in stat_block.action:
        attack = _parse_monster_attack(action)
        if attack is not None:
            attacks.append(attack)
    return attacks


def _parse_monster_attack(action: BestiaryActionSchema) -> MonsterAttack | None:
    if isinstance(action.mechanics, AttackActionMechanicsSchema):
        damage = [
            effect
            for effect in action.mechanics.hit
            if isinstance(effect, DamageEffectSchema)
        ]
        if not damage:
            return None
        primary, *additional = damage
        return MonsterAttack(
            name=action.name,
            attack_modes=tuple(action.mechanics.attack_modes),
            attack_bonus=action.mechanics.attack_bonus,
            damage_dice=primary.dice,
            damage_bonus=primary.bonus,
            damage_type=primary.damage_type,
            range_normal=action.mechanics.range_normal_feet,
            range_long=action.mechanics.range_long_feet,
            additional_damage=tuple(
                MonsterAttackDamage(
                    dice=component.dice,
                    bonus=component.bonus,
                    damage_type=component.damage_type,
                )
                for component in additional
            ),
            hit_effects=tuple(
                ActionEffect(
                    kind=effect.type,
                    parameters=effect.model_dump(
                        exclude={"type"},
                        exclude_none=True,
                    ),
                )
                for effect in action.mechanics.hit
                if not isinstance(effect, DamageEffectSchema)
            ),
            reach_feet=action.mechanics.reach_feet,
        )
    if not action.entries:
        return None
    entry = action.entries[0]
    if not isinstance(entry, str):
        return None

    attack_tag = re.search(r"\{@atk(?:r)?\s+([^}]+)\}", entry)
    hit = re.search(r"\{@hit\s+([+-]?\d+)\}", entry)
    damage = re.search(r"\{@damage\s+(\d+d\d+)(?:\s*\+\s*(\d+))?\}", entry)
    damage_type = re.search(r"\{@damage[^}]+\}\)?\s*([A-Za-z]+)\s+damage", entry)
    if attack_tag is None or hit is None or damage is None or damage_type is None:
        return None

    attack_modes = _parse_attack_modes(attack_tag.group(1))
    if not attack_modes:
        return None

    range_match = re.search(r"range\s+(\d+)\/(\d+)\s*ft", entry)
    return MonsterAttack(
        name=action.name,
        attack_modes=attack_modes,
        attack_bonus=int(hit.group(1)),
        damage_dice=damage.group(1),
        damage_bonus=int(damage.group(2) or 0),
        damage_type=damage_type.group(1).lower(),
        range_normal=int(range_match.group(1)) if range_match is not None else None,
        range_long=int(range_match.group(2)) if range_match is not None else None,
    )


def _parse_attack_modes(value: str) -> tuple[str, ...]:
    modes: list[str] = []
    for token in value.split(","):
        token = token.strip()
        if "m" in token and "melee" not in modes:
            modes.append("melee")
        if "r" in token and "ranged" not in modes:
            modes.append("ranged")
    return tuple(modes)
