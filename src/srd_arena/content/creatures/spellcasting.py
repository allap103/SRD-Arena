from srd_arena.content.classes.schema import ClassSchema, SubclassSchema
from srd_arena.domain.creatures import Attributes

SpellcastingSource = ClassSchema | SubclassSchema


def spellcasting_ability_score(attributes: Attributes, ability: str) -> int:
    ability_map = {
        "str": attributes.strength, "dex": attributes.dexterity,
        "con": attributes.constitution, "int": attributes.intelligence,
        "wis": attributes.wisdom, "cha": attributes.charisma,
    }
    return ability_map.get(ability.casefold(), 10)


def spell_preparation_mode(block: SpellcastingSource) -> str:
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


def spell_slots_progression(
    block: SpellcastingSource,
    level: int,
) -> dict[int, int]:
    row_index = level - 1
    for group in block.table_groups:
        rows = group.spell_progression_rows
        if row_index < 0 or row_index >= len(rows):
            continue
        row = rows[row_index]
        return {
            spell_level: slots
            for spell_level, slots in enumerate(row, start=1)
            if isinstance(slots, int) and slots > 0
        }
    return {}


def spell_count_progression(
    block: SpellcastingSource,
    level: int,
) -> int | None:
    direct = progression_value(block.spells_known_progression, level)
    if direct is not None:
        return direct
    row_index = level - 1
    for group in block.table_groups:
        labels, rows = group.column_labels, group.rows
        if not any(
            isinstance(label, str) and ("Spells Known" in label or "Spells Prepared" in label)
            for label in labels
        ) or row_index < 0 or row_index >= len(rows):
            continue
        row = rows[row_index]
        if row:
            return int(row[0]) if isinstance(row[0], int) else None
    return None
