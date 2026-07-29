from ...domain.creatures import Attributes


def spellcasting_ability_score(attributes: Attributes, ability: str) -> int:
    ability_map = {
        "str": attributes.strength,
        "dex": attributes.dexterity,
        "con": attributes.constitution,
        "int": attributes.intelligence,
        "wis": attributes.wisdom,
        "cha": attributes.charisma,
    }
    return ability_map.get(ability.casefold(), 10)


def spell_preparation_mode(block: dict) -> str:
    # The supported source formats currently describe fixed known/prepared lists.
    return "fixed"


def progression_value(progression: object, level: int) -> int | None:
    if not isinstance(progression, list):
        return None
    row_index = level - 1
    if row_index < 0 or row_index >= len(progression):
        return None
    value = progression[row_index]
    return int(value) if isinstance(value, int) else None


def spell_slots_progression(block: dict, level: int) -> dict[int, int]:
    groups = block.get("subclassTableGroups") or block.get("classTableGroups") or []
    if not isinstance(groups, list):
        return {}
    row_index = level - 1
    for group in groups:
        if not isinstance(group, dict):
            continue
        rows = group.get("rowsSpellProgression")
        if not isinstance(rows, list) or row_index < 0 or row_index >= len(rows):
            continue
        row = rows[row_index]
        if isinstance(row, list):
            return {
                spell_level: slots
                for spell_level, slots in enumerate(row, start=1)
                if isinstance(slots, int) and slots > 0
            }
    return {}


def spell_count_progression(block: dict, level: int) -> int | None:
    direct = progression_value(block.get("spellsKnownProgression"), level)
    if direct is not None:
        return direct
    groups = block.get("subclassTableGroups") or block.get("classTableGroups") or []
    if not isinstance(groups, list):
        return None
    row_index = level - 1
    for group in groups:
        if not isinstance(group, dict):
            continue
        labels, rows = group.get("colLabels"), group.get("rows")
        if not isinstance(labels, list) or not isinstance(rows, list):
            continue
        if (
            not any(
                isinstance(label, str)
                and ("Spells Known" in label or "Spells Prepared" in label)
                for label in labels
            )
            or row_index < 0
            or row_index >= len(rows)
        ):
            continue
        row = rows[row_index]
        if isinstance(row, list) and row:
            return int(row[0]) if isinstance(row[0], int) else None
    return None
