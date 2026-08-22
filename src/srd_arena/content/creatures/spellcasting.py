from srd_arena.content.character_options.classes import ClassRecord, SubclassRecord
from srd_arena.content.character_options.classes.schema import (
    ClassSchema,
    SubclassSchema,
)
from srd_arena.content.spells import SpellCatalog, build_spell
from srd_arena.domain.creatures import Attributes, Spellcasting

from .schema import CreatureSchema

SpellcastingSource = ClassSchema | SubclassSchema


def build_spellcasting(
    schema: CreatureSchema,
    attributes: Attributes,
    class_record: ClassRecord | None,
    subclass_record: SubclassRecord | None,
    spells: SpellCatalog | None,
) -> Spellcasting | None:
    if schema.spellcasting is not None:
        config = schema.spellcasting
        ability_modifier = (
            spellcasting_ability_score(attributes, config.ability) - 10
        ) // 2
        spell_slots_max = dict(config.spell_slots)
        return Spellcasting(
            ability=config.ability,
            ability_modifier=ability_modifier,
            save_dc=8 + attributes.proficiency_bonus + ability_modifier,
            attack_bonus=attributes.proficiency_bonus + ability_modifier,
            caster_progression=config.caster_progression,
            preparation_mode=config.preparation_mode,
            cantrips_known=config.cantrips_known,
            spell_count=config.spell_count,
            spell_slots_max=spell_slots_max,
            spell_slots_remaining=dict(spell_slots_max),
            learned_spells=[
                build_spell(reference.name, reference.source, spells)
                for reference in schema.spells_known
            ],
        )

    source_definition = _spellcasting_source_definition(
        class_record,
        subclass_record,
    )
    if source_definition is None:
        return None

    ability = source_definition.spellcasting_ability
    caster_progression = source_definition.caster_progression
    if ability is None or caster_progression is None:
        return None

    level = attributes.level
    ability_modifier = (
        spellcasting_ability_score(attributes, ability) - 10
    ) // 2
    spell_slots_max = spell_slots_progression(source_definition, level)
    return Spellcasting(
        ability=ability,
        ability_modifier=ability_modifier,
        save_dc=8 + attributes.proficiency_bonus + ability_modifier,
        attack_bonus=attributes.proficiency_bonus + ability_modifier,
        caster_progression=caster_progression,
        preparation_mode=spell_preparation_mode(source_definition),
        cantrips_known=(
            progression_value(source_definition.cantrip_progression, level) or 0
        ),
        spell_count=spell_count_progression(source_definition, level),
        spell_slots_max=spell_slots_max,
        spell_slots_remaining=dict(spell_slots_max),
        learned_spells=[
            build_spell(reference.name, reference.source, spells)
            for reference in schema.spells_known
        ],
    )


def _spellcasting_source_definition(
    class_record: ClassRecord | None,
    subclass_record: SubclassRecord | None,
) -> SpellcastingSource | None:
    definitions: tuple[SpellcastingSource | None, ...] = (
        subclass_record.definition if subclass_record else None,
        class_record.definition if class_record else None,
    )
    return next(
        (
            definition
            for definition in definitions
            if definition is not None
            and definition.spellcasting_ability is not None
            and definition.caster_progression is not None
        ),
        None,
    )


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
