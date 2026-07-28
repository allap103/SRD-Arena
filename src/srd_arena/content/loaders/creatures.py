from pathlib import Path
import re
from typing import cast

from srd_arena.content.catalogs import (
    BestiaryCatalog,
    ClassCatalog,
    ClassRecord,
    OptionalFeatureCatalog,
    SpellCatalog,
    SubclassCatalog,
    SubclassRecord,
)
from srd_arena.content.normalization import normalize_optional_feature_effects
from srd_arena.content.schemas import CreatureSchema, OptionalFeatureSchema
from srd_arena.content.schemas.bestiary import BestiaryMonsterSchema
from srd_arena.content.schemas.classes import (
    ClassFeatureReferenceSchema,
    ClassFeatureSchema,
    ClassSchema,
    SubclassSchema,
)
from srd_arena.content.schemas.creature import CreatureItemReferenceSchema
from srd_arena.content.sources import load_json, slug
from srd_arena.content.translators import build_spell
from srd_arena.domain.creatures import (
    Attributes,
    ClassFeature,
    ClassRef,
    Creature,
    Equipment,
    Inventory,
    SubclassRef,
)
from srd_arena.domain.creatures import Spellcasting
from srd_arena.domain.effects.triggered import TriggeredEffect
from .monster_attacks import build_monster_attacks
from .multiattacks import build_multiattack
from .creature_attributes import build_creature_attributes, build_creature_size
from .creature_features import build_combat_profile, build_feature_uses_remaining
from .creature_spellcasting import (
    progression_value as _progression_value,
    spell_count_progression as _spell_count_progression,
    spell_preparation_mode as _spell_preparation_mode,
    spell_slots_progression as _spell_slots_progression,
    spellcasting_ability_score as _spellcasting_ability_score,
)
from .creature_statistics import build_creature_statistics
from .player_characters import PlayerCharacterTemplates


def load_creature(
    path: str | Path,
    bestiary: BestiaryCatalog | None = None,
    classes: ClassCatalog | None = None,
    player_characters: PlayerCharacterTemplates | None = None,
    optional_features: OptionalFeatureCatalog | None = None,
    subclasses: SubclassCatalog | None = None,
    spells: SpellCatalog | None = None,
) -> Creature:
    return build_creature(
        CreatureSchema.model_validate(load_json(path)),
        bestiary,
        classes,
        player_characters,
        optional_features,
        subclasses,
        spells,
    )


def build_creature(
    schema: CreatureSchema,
    bestiary: BestiaryCatalog | None = None,
    classes: ClassCatalog | None = None,
    player_characters: PlayerCharacterTemplates | None = None,
    optional_features: OptionalFeatureCatalog | None = None,
    subclasses: SubclassCatalog | None = None,
    spells: SpellCatalog | None = None,
) -> Creature:
    schema = _resolve_creature_schema(schema, player_characters)
    stat_block = _find_bestiary_monster(schema, bestiary)
    class_record = _find_class_record(schema, classes)
    subclass_record = _find_subclass_record(schema, subclasses, class_record)
    equipment = Equipment(
        equipped_items={
            **Equipment().equipped_items,
            **{
                slot: _creature_item_id(item)
                for slot, item in cast(dict[str, object], dict(schema.equipment)).items()
            },
        }
    )
    attributes = build_creature_attributes(schema, stat_block, class_record)
    class_features = _resolve_class_features(class_record, schema.attributes.level)
    class_features.extend(
        _resolve_subclass_features(
            subclass_record,
            schema.attributes.level,
            class_name=schema.class_ref.name if schema.class_ref else None,
        )
    )
    triggered_effects = _resolve_optional_feature_effects(schema, optional_features)
    combat_profile = build_combat_profile(class_features)
    spellcasting = _build_spellcasting(
        schema,
        attributes,
        class_record,
        subclass_record,
        spells,
    )

    monster_attacks = build_monster_attacks(stat_block)
    multiattack_action = (
        next(
            (
                action
                for action in stat_block.action
                if action.mechanics is not None
                and action.mechanics.type == "multiattack"
            ),
            None,
        )
        if stat_block is not None
        else None
    )
    return Creature(
        id=schema.id,
        name=schema.name or _stat_block_name(stat_block),
        description=schema.description,
        token_image=schema.token_image,
        inventory=Inventory(items=[_creature_item_id(item) for item in schema.inventory]),
        attributes=attributes,
        equipment=equipment,
        size=build_creature_size(schema, stat_block),
        class_ref=(
            ClassRef(name=schema.class_ref.name, source=schema.class_ref.source)
            if schema.class_ref
            else None
        ),
        subclass_ref=(
            SubclassRef(
                name=schema.subclass_ref.name,
                source=schema.subclass_ref.source,
                class_name=schema.subclass_ref.class_name,
                class_source=schema.subclass_ref.class_source,
            )
            if schema.subclass_ref
            else None
        ),
        class_features=class_features,
        triggered_effects=triggered_effects,
        combat_profile=combat_profile,
        feature_uses_remaining=build_feature_uses_remaining(combat_profile),
        monster_attacks=monster_attacks,
        multiattack=build_multiattack(
            multiattack_action.mechanics
            if multiattack_action is not None
            else None
        ),
        spellcasting=spellcasting,
        statistics=build_creature_statistics(stat_block),
        max_health_override=(
            stat_block.average_hit_points
            if stat_block is not None
            else None
        ),
    )


def _resolve_creature_schema(
    instance: CreatureSchema,
    player_characters: PlayerCharacterTemplates | None,
) -> CreatureSchema:
    if instance.player_character is None:
        return instance
    if player_characters is None:
        raise ValueError(
            f"Creature '{instance.id}' references player character "
            f"'{instance.player_character}', but no player character catalog was loaded."
        )
    template = player_characters.get(instance.player_character)
    if template is None:
        raise KeyError(f"Player character '{instance.player_character}' not found.")

    template_data = template.model_dump(exclude={"id", "player_character"})
    instance_data = instance.model_dump(
        exclude_unset=True,
        exclude={
            "attributes",
            "player_character",
            "equipment",
            "inventory",
            "metadata",
            "optional_features",
            "spells_known",
        },
    )
    if "attributes" in instance.model_fields_set:
        instance_data["attributes"] = instance.attributes.model_dump()
    merged = {
        **template_data,
        **instance_data,
        "inventory": [
            *template.inventory,
            *instance.inventory,
        ],
        "equipment": {
            **template.equipment,
            **instance.equipment,
        },
        "metadata": {
            **template.metadata,
            **instance.metadata,
        },
        "optional_features": [
            *template.optional_features,
            *instance.optional_features,
        ],
        "spells_known": [
            *template.spells_known,
            *instance.spells_known,
        ],
    }
    return CreatureSchema.model_validate(merged)


def _resolve_optional_feature_effects(
    schema: CreatureSchema,
    catalog: OptionalFeatureCatalog | None,
) -> list[TriggeredEffect]:
    effects: list[TriggeredEffect] = []
    for reference in schema.optional_features:
        if catalog is None:
            raise ValueError(
                f"Creature references optional feature '{reference.name}', "
                "but no optional feature catalog was loaded."
            )
        try:
            feature = catalog.find(reference.name, reference.source)
        except KeyError:
            normalized = normalize_optional_feature_effects(
                OptionalFeatureSchema(
                    name=reference.name,
                    source=reference.source or "",
                )
            )
            if not normalized:
                raise
            effects.extend(normalized)
        else:
            effects.extend(normalize_optional_feature_effects(feature))
    return effects


def _find_class_record(
    schema: CreatureSchema,
    classes: ClassCatalog | None,
) -> ClassRecord | None:
    if schema.class_ref is None:
        return None
    if classes is None:
        raise ValueError(
            f"Creature references class '{schema.class_ref.name}', "
            "but no class catalog was loaded."
        )
    return classes.find(schema.class_ref.name, schema.class_ref.source)


def _find_subclass_record(
    schema: CreatureSchema,
    subclasses: SubclassCatalog | None,
    class_record: ClassRecord | None,
) -> SubclassRecord | None:
    reference = schema.subclass_ref
    if reference is None:
        return None
    if subclasses is None:
        raise ValueError(
            f"Creature references subclass '{reference.name}', "
            "but no subclass catalog was loaded."
        )
    class_name = (
        reference.class_name
        or (class_record.definition.public_name if class_record else None)
    )
    if class_name is None:
        raise ValueError(
            f"Subclass '{reference.name}' requires a class name."
        )
    class_source = (
        reference.class_source
        or (class_record.definition.source if class_record else None)
    )
    return subclasses.find(
        reference.name,
        reference.source,
        class_name,
        class_source,
    )


def _creature_item_id(item: str | CreatureItemReferenceSchema | object) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, CreatureItemReferenceSchema):
        return slug(item.name)
    if isinstance(item, dict):
        name = item.get("name")
        if isinstance(name, str):
            return slug(name)
    raise TypeError(f"Unsupported creature item reference: {item!r}")


def _resolve_class_features(
    class_record: ClassRecord | None,
    level: int,
) -> list[ClassFeature]:
    if class_record is None:
        return []

    definition = class_record.definition
    class_features: list[ClassFeature] = []

    for feature_ref in definition.class_features:
        parsed = _parse_class_feature_reference(feature_ref)
        if parsed is None:
            continue
        feature_name, feature_level = parsed
        if feature_level > level:
            continue
        class_feature = _normalize_class_feature(
            definition.public_name,
            feature_name,
            feature_level,
            class_record,
            level,
        )
        if class_feature is not None:
            class_features.append(class_feature)
    return class_features


def _resolve_subclass_features(
    subclass_record: SubclassRecord | None,
    level: int,
    *,
    class_name: str | None,
) -> list[ClassFeature]:
    if subclass_record is None:
        return []

    definition = subclass_record.definition
    class_features: list[ClassFeature] = []

    for feature_ref in definition.subclass_features:
        parsed = _parse_class_feature_reference(feature_ref)
        if parsed is None:
            continue
        feature_name, feature_level = parsed
        if feature_level > level:
            continue
        class_feature = _normalize_class_feature(
            class_name or definition.class_name,
            feature_name,
            feature_level,
            source_subclass=definition.public_name,
        )
        if class_feature is not None:
            class_features.append(class_feature)
    return class_features


def _parse_class_feature_reference(
    feature_ref: str | ClassFeatureReferenceSchema,
) -> tuple[str, int] | None:
    raw_ref = (
        feature_ref
        if isinstance(feature_ref, str)
        else feature_ref.class_feature
    )
    parts = raw_ref.split("|")
    if not parts:
        return None
    for part in reversed(parts):
        if part.isdigit():
            return (parts[0], int(part))
    return None


def _normalize_class_feature(
    class_name: str,
    feature_name: str,
    feature_level: int,
    class_record: ClassRecord | None = None,
    creature_level: int = 1,
    source_subclass: str | None = None,
) -> ClassFeature | None:
    extra_attack_counts = {
        "Extra Attack": 2,
        "Extra Attack (2)": 3,
        "Extra Attack (3)": 4,
        "Extra Attack Improvement": 2,
    }
    attacks = extra_attack_counts.get(feature_name)
    if attacks is None:
        if feature_name == "Second Wind":
            return ClassFeature(
                id="second_wind",
                name=feature_name,
                source_class=class_name,
                level=feature_level,
                source_subclass=source_subclass,
                data={
                    "uses": _second_wind_uses(class_record, creature_level),
                    **_second_wind_healing_dice(
                        class_record,
                        feature_name,
                        feature_level,
                    ),
                },
            )
        if feature_name == "Action Surge":
            return ClassFeature(
                id="action_surge",
                name=feature_name,
                source_class=class_name,
                level=feature_level,
                source_subclass=source_subclass,
                data={"uses": _action_surge_uses(class_record, creature_level)},
            )
        else:
            return None
    return ClassFeature(
        id="extra_attack",
        name=feature_name,
        source_class=class_name,
        level=feature_level,
        source_subclass=source_subclass,
        data={"attacks": attacks},
    )


def _build_spellcasting(
    schema: CreatureSchema,
    attributes: Attributes,
    class_record: ClassRecord | None,
    subclass_record: SubclassRecord | None,
    spells: SpellCatalog | None,
) -> Spellcasting | None:
    if schema.spellcasting is not None:
        config = schema.spellcasting
        ability_score = _spellcasting_ability_score(attributes, config.ability)
        ability_modifier = (ability_score - 10) // 2
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
    ability_score = _spellcasting_ability_score(attributes, ability)
    ability_modifier = (ability_score - 10) // 2
    spell_slots_max = _spell_slots_progression(source_definition, level)
    learned_spells = [
        build_spell(reference.name, reference.source, spells)
        for reference in schema.spells_known
    ]

    return Spellcasting(
        ability=ability,
        ability_modifier=ability_modifier,
        save_dc=8 + attributes.proficiency_bonus + ability_modifier,
        attack_bonus=attributes.proficiency_bonus + ability_modifier,
        caster_progression=caster_progression,
        preparation_mode=_spell_preparation_mode(source_definition),
        cantrips_known=(
            _progression_value(source_definition.cantrip_progression, level) or 0
        ),
        spell_count=_spell_count_progression(source_definition, level),
        spell_slots_max=spell_slots_max,
        spell_slots_remaining=dict(spell_slots_max),
        learned_spells=learned_spells,
    )


def _spellcasting_source_definition(
    class_record: ClassRecord | None,
    subclass_record: SubclassRecord | None,
) -> ClassSchema | SubclassSchema | None:
    definitions: tuple[ClassSchema | SubclassSchema | None, ...] = (
        subclass_record.definition if subclass_record else None,
        class_record.definition if class_record else None,
    )
    for definition in definitions:
        if (
            definition is not None
            and definition.spellcasting_ability is not None
            and definition.caster_progression is not None
        ):
            return definition
    return None


def _second_wind_uses(
    class_record: ClassRecord | None,
    feature_level: int,
) -> int:
    if class_record is None:
        return 1
    if class_record.definition.source != "XPHB":
        return 1
    table_value = _class_table_value(
        class_record.definition,
        "Second Wind",
        feature_level,
    )
    if table_value is None:
        return 2
    try:
        return int(table_value)
    except ValueError:
        return 2


def _action_surge_uses(
    class_record: ClassRecord | None,
    feature_level: int,
) -> int:
    if class_record is None:
        return 1
    table_value = _class_table_value(
        class_record.definition,
        "Action Surge",
        feature_level,
    )
    if table_value is None:
        return 1
    try:
        return int(table_value)
    except ValueError:
        return 1


def _second_wind_healing_dice(
    class_record: ClassRecord | None,
    feature_name: str,
    feature_level: int,
) -> dict[str, int]:
    feature_entry = _class_feature_entry(
        class_record,
        feature_name,
        feature_level,
    )
    dice = _first_dice_expression(
        feature_entry.entries if feature_entry is not None else None
    )
    if dice is None:
        return {
            "healing_die_count": 1,
            "healing_die_sides": 10,
        }
    dice_count, dice_sides = dice
    return {
        "healing_die_count": dice_count,
        "healing_die_sides": dice_sides,
    }


def _class_feature_entry(
    class_record: ClassRecord | None,
    feature_name: str,
    feature_level: int,
) -> ClassFeatureSchema | None:
    if class_record is None:
        return None
    definition = class_record.definition
    for entry in class_record.features:
        if entry.public_name != feature_name or entry.level != feature_level:
            continue
        if entry.class_name != definition.name:
            continue
        if entry.class_source != definition.source:
            continue
        return entry
    return None


def _first_dice_expression(value: object) -> tuple[int, int] | None:
    if isinstance(value, str):
        match = re.search(r"\{@dice\s+(\d+)d(\d+)", value)
        if match is None:
            return None
        return int(match.group(1)), int(match.group(2))
    if isinstance(value, dict):
        for nested_value in value.values():
            dice = _first_dice_expression(nested_value)
            if dice is not None:
                return dice
        return None
    if isinstance(value, list):
        for item in value:
            dice = _first_dice_expression(item)
            if dice is not None:
                return dice
    return None


def _class_table_value(
    definition: ClassSchema,
    column_label: str,
    level: int,
) -> str | None:
    for group in definition.table_groups:
        labels = group.column_labels
        rows = group.rows
        try:
            column_index = labels.index(column_label)
        except ValueError:
            continue
        row_index = level - 1
        if row_index < 0 or row_index >= len(rows):
            continue
        row = rows[row_index]
        if not isinstance(row, list) or column_index >= len(row):
            continue
        value = row[column_index]
        return str(value)
    return None


def _find_bestiary_monster(
    schema: CreatureSchema,
    bestiary: BestiaryCatalog | None,
) -> BestiaryMonsterSchema | None:
    if schema.stat_block is None:
        return None
    if bestiary is None:
        raise ValueError(
            f"Creature references stat block '{schema.stat_block.name}', "
            "but no bestiary catalog was loaded."
        )
    return bestiary.find(schema.stat_block.name, schema.stat_block.source)


def _stat_block_name(stat_block: BestiaryMonsterSchema | None) -> str:
    if stat_block is None:
        raise ValueError("Creature must define either 'name' or 'stat_block'.")
    return stat_block.public_name
