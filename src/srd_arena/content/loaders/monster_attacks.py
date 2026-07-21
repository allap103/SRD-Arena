import re

from ...domain.creatures.monster_attack import MonsterAttack


def build_monster_attacks(stat_block: dict | None) -> list[MonsterAttack]:
    if stat_block is None:
        return []
    attacks: list[MonsterAttack] = []
    for action in stat_block.get("action", []):
        if not isinstance(action, dict):
            continue
        attack = _parse_monster_attack(action)
        if attack is not None:
            attacks.append(attack)
    return attacks


def _parse_monster_attack(action: dict) -> MonsterAttack | None:
    name = action.get("name")
    entries = action.get("entries")
    if not isinstance(name, str) or not isinstance(entries, list) or not entries:
        return None
    entry = entries[0]
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
        name=name,
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
