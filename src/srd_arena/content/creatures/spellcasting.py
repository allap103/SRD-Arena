"""Build creature-specific spellcasting grants from authored progressions."""

from srd_arena.content.character_options.classes import ClassRecord, SubclassRecord
from srd_arena.content.character_options.classes.schema import (
    ClassSchema,
    SubclassSchema,
)
from srd_arena.content.spells import SpellCatalog, build_spell
from srd_arena.domain.creatures import Attributes, Spellcasting
from srd_arena.domain.spells import Spell

from .schema import CreatureSchema

SpellcastingSource = ClassSchema | SubclassSchema


def build_spellcasting(
    schema: CreatureSchema,
    attributes: Attributes,
    class_record: ClassRecord | None,
    subclass_record: SubclassRecord | None,
    spells: SpellCatalog | None,
) -> Spellcasting | None:
    """Bind spell definitions to a creature's casting statistics and resource pools."""

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
                _build_referenced_spell(reference.name, reference.source, spells)
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
    ability_modifier = (spellcasting_ability_score(attributes, ability) - 10) // 2
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
            _build_referenced_spell(reference.name, reference.source, spells)
            for reference in schema.spells_known
        ],
    )


def _build_referenced_spell(
    name: str,
    source: str | None,
    catalog: SpellCatalog | None,
) -> Spell:
    if catalog is None:
        raise ValueError(
            f"Creature references spell '{name}', but no spell catalog was loaded."
        )
    return build_spell(catalog.find(name, source))


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
    """Return the creature ability score used by an authored spellcasting entry.

    >>> attributes = Attributes(10, 5, 8, 12, 10, 14, 16, 10, 10)
    >>> spellcasting_ability_score(attributes, "int")
    16
    >>> spellcasting_ability_score(attributes, "unknown")
    10
    """

    ability_map = {
        "str": attributes.strength,
        "dex": attributes.dexterity,
        "con": attributes.constitution,
        "int": attributes.intelligence,
        "wis": attributes.wisdom,
        "cha": attributes.charisma,
    }
    return ability_map.get(ability.casefold(), 10)


def spell_preparation_mode(block: SpellcastingSource) -> str:
    # The supported source formats currently describe fixed known/prepared lists.
    """Return the fixed-list preparation mode supported by current source formats.

    >>> from types import SimpleNamespace
    >>> spell_preparation_mode(SimpleNamespace())
    'fixed'
    """

    return "fixed"


def progression_value(progression: object, level: int) -> int | None:
    """Read the value in effect at a level from a sparse authored progression.

    >>> progression_value([2, 3, None], 2)
    3
    >>> progression_value([2, 3, None], 3) is None
    True
    """

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
    """Derive per-level spell-slot maxima from a class progression table.

    >>> from types import SimpleNamespace
    >>> group = SimpleNamespace(spell_progression_rows=[[2, 1, 0]])
    >>> spell_slots_progression(SimpleNamespace(table_groups=[group]), 1)
    {1: 2, 2: 1}
    """

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
    """Derive the known or prepared spell count across class levels.

    >>> from types import SimpleNamespace
    >>> block = SimpleNamespace(spells_known_progression=[2, 3], table_groups=[])
    >>> spell_count_progression(block, 2)
    3
    """

    direct = progression_value(block.spells_known_progression, level)
    if direct is not None:
        return direct
    row_index = level - 1
    for group in block.table_groups:
        labels, rows = group.column_labels, group.rows
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
        if row:
            return int(row[0]) if isinstance(row[0], int) else None
    return None
