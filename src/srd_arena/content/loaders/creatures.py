from pathlib import Path
import re
from typing import cast

from ..schemas import CreatureSchema
from ..schemas.creature import CreatureItemReferenceSchema
from ...domain.creatures import (
    Attributes,
    ClassFeature,
    ClassRef,
    Creature,
    Equipment,
    Inventory,
    SubclassRef,
)
from ...domain.actions.spells import Spell
from ...domain.creatures import Spellcasting
from ...domain.effects.triggered import TriggeredEffect
from ..normalization import normalize_optional_feature_effects
from .catalogs import (
    _find_class_block,
    _find_optional_feature,
    _find_spell,
    _find_stat_block,
    _find_subclass_block,
)
from .source_data import _load_json, _slug
from .monster_attacks import build_monster_attacks
from .creature_attributes import build_creature_attributes, build_creature_size
from .creature_features import build_combat_profile, build_feature_uses_remaining
from .creature_spellcasting import (
    progression_value as _progression_value,
    spell_count_progression as _spell_count_progression,
    spell_preparation_mode as _spell_preparation_mode,
    spell_slots_progression as _spell_slots_progression,
    spellcasting_ability_score as _spellcasting_ability_score,
)
from .types import (
    ClassCatalog,
    PlayerCharacterCatalog,
    OptionalFeatureCatalog,
    SpellCatalog,
    StatBlockCatalog,
    SubclassCatalog,
)


def load_creature(
    path: str | Path,
    stat_blocks: StatBlockCatalog | None = None,
    class_blocks: ClassCatalog | None = None,
    player_characters: PlayerCharacterCatalog | None = None,
    optional_features: OptionalFeatureCatalog | None = None,
    subclass_blocks: SubclassCatalog | None = None,
    spell_catalog: SpellCatalog | None = None,
) -> Creature:
    return build_creature(
        CreatureSchema.model_validate(_load_json(path)),
        stat_blocks,
        class_blocks,
        player_characters,
        optional_features,
        subclass_blocks,
        spell_catalog,
    )


def build_creature(
    schema: CreatureSchema,
    stat_blocks: StatBlockCatalog | None = None,
    class_blocks: ClassCatalog | None = None,
    player_characters: PlayerCharacterCatalog | None = None,
    optional_features: OptionalFeatureCatalog | None = None,
    subclass_blocks: SubclassCatalog | None = None,
    spell_catalog: SpellCatalog | None = None,
) -> Creature:
    schema = _resolve_creature_schema(schema, player_characters)
    stat_block = (
        _find_stat_block(schema.stat_block.name, schema.stat_block.source, stat_blocks)
        if schema.stat_block
        else None
    )
    class_block = (
        _find_class_block(schema.class_ref.name, schema.class_ref.source, class_blocks)
        if schema.class_ref
        else None
    )
    subclass_block = (
        _find_subclass_block(schema.subclass_ref, subclass_blocks, class_block)
        if schema.subclass_ref
        else None
    )
    equipment = Equipment(
        equipped_items={
            **Equipment().equipped_items,
            **{
                slot: _creature_item_id(item)
                for slot, item in cast(
                    dict[str, object], dict(schema.equipment)
                ).items()
            },
        }
    )
    attributes = build_creature_attributes(schema, stat_block, class_block)
    class_features = _resolve_class_features(class_block, schema.attributes.level)
    class_features.extend(
        _resolve_subclass_features(
            subclass_block,
            schema.attributes.level,
            class_name=schema.class_ref.name if schema.class_ref else None,
        )
    )
    triggered_effects = _resolve_optional_feature_effects(schema, optional_features)
    combat_profile = build_combat_profile(class_features)
    spellcasting = _build_spellcasting(
        schema,
        attributes,
        class_block,
        subclass_block,
        spell_catalog,
    )

    return Creature(
        id=schema.id,
        name=schema.name or _stat_block_name(stat_block),
        description=schema.description,
        token_image=schema.token_image,
        inventory=Inventory(
            items=[_creature_item_id(item) for item in schema.inventory]
        ),
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
        monster_attacks=build_monster_attacks(stat_block),
        spellcasting=spellcasting,
    )


def _resolve_creature_schema(
    instance: CreatureSchema,
    player_characters: PlayerCharacterCatalog | None,
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
            feature = _find_optional_feature(reference.name, reference.source, catalog)
        except KeyError:
            normalized = normalize_optional_feature_effects(
                {"name": reference.name, "source": reference.source or ""}
            )
            if not normalized:
                raise
            effects.extend(normalized)
        else:
            effects.extend(normalize_optional_feature_effects(feature))
    return effects


def _creature_item_id(item: str | CreatureItemReferenceSchema | object) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, CreatureItemReferenceSchema):
        return _slug(item.name)
    if isinstance(item, dict):
        name = item.get("name")
        if isinstance(name, str):
            return _slug(name)
    raise TypeError(f"Unsupported creature item reference: {item!r}")


def _resolve_class_features(
    class_block: dict | None,
    level: int,
) -> list[ClassFeature]:
    if class_block is None:
        return []

    class_name = str(class_block.get("name", ""))
    features = class_block.get("classFeatures", [])
    class_features: list[ClassFeature] = []
    if not isinstance(features, list):
        return class_features

    for feature_ref in features:
        parsed = _parse_class_feature_reference(feature_ref)
        if parsed is None:
            continue
        feature_name, feature_level = parsed
        if feature_level > level:
            continue
        class_feature = _normalize_class_feature(
            class_name,
            feature_name,
            feature_level,
            class_block,
            level,
        )
        if class_feature is not None:
            class_features.append(class_feature)
    return class_features


def _resolve_subclass_features(
    subclass_block: dict | None,
    level: int,
    *,
    class_name: str | None,
) -> list[ClassFeature]:
    if subclass_block is None:
        return []

    subclass_name = str(subclass_block.get("name", ""))
    features = subclass_block.get("subclassFeatures", [])
    class_features: list[ClassFeature] = []
    if not isinstance(features, list):
        return class_features

    for feature_ref in features:
        parsed = _parse_class_feature_reference(feature_ref)
        if parsed is None:
            continue
        feature_name, feature_level = parsed
        if feature_level > level:
            continue
        class_feature = _normalize_class_feature(
            class_name or str(subclass_block.get("className", "")),
            feature_name,
            feature_level,
            source_subclass=subclass_name,
        )
        if class_feature is not None:
            class_features.append(class_feature)
    return class_features


def _parse_class_feature_reference(
    feature_ref: str | dict[str, object],
) -> tuple[str, int] | None:
    raw_ref = (
        feature_ref if isinstance(feature_ref, str) else feature_ref.get("classFeature")
    )
    if not isinstance(raw_ref, str):
        return None
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
    class_block: dict | None = None,
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
                    "uses": _second_wind_uses(class_block, creature_level),
                    **_second_wind_healing_dice(
                        class_block, feature_name, feature_level
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
                data={"uses": _action_surge_uses(class_block, creature_level)},
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
    class_block: dict | None,
    subclass_block: dict | None,
    spell_catalog: SpellCatalog | None,
) -> Spellcasting | None:
    source_block = _spellcasting_source_block(class_block, subclass_block)
    if source_block is None:
        return None

    ability = source_block.get("spellcastingAbility")
    caster_progression = source_block.get("casterProgression")
    if not isinstance(ability, str) or not isinstance(caster_progression, str):
        return None

    level = attributes.level
    ability_score = _spellcasting_ability_score(attributes, ability)
    ability_modifier = (ability_score - 10) // 2
    spell_slots_max = _spell_slots_progression(source_block, level)
    learned_spells = [
        _build_spell(reference.name, reference.source, spell_catalog)
        for reference in schema.spells_known
    ]

    return Spellcasting(
        ability=ability,
        ability_modifier=ability_modifier,
        save_dc=8 + attributes.proficiency_bonus + ability_modifier,
        attack_bonus=attributes.proficiency_bonus + ability_modifier,
        caster_progression=caster_progression,
        preparation_mode=_spell_preparation_mode(source_block),
        cantrips_known=_progression_value(source_block.get("cantripProgression"), level)
        or 0,
        spell_count=_spell_count_progression(source_block, level),
        spell_slots_max=spell_slots_max,
        spell_slots_remaining=dict(spell_slots_max),
        learned_spells=learned_spells,
    )


def _spellcasting_source_block(
    class_block: dict | None,
    subclass_block: dict | None,
) -> dict | None:
    for block in (subclass_block, class_block):
        if not isinstance(block, dict):
            continue
        if isinstance(block.get("spellcastingAbility"), str) and isinstance(
            block.get("casterProgression"),
            str,
        ):
            return block
    return None


def _build_spell(
    name: str,
    source: str | None,
    spell_catalog: SpellCatalog | None,
) -> Spell:
    raw = _find_spell(name, source, spell_catalog)
    return Spell(
        id=_slug(name),
        name=name,
        source=source,
        level=int(raw.get("level", 0)),
        school=raw.get("school") if isinstance(raw.get("school"), str) else None,
        casting_time=tuple(
            entry for entry in raw.get("time", []) if isinstance(entry, dict)
        ),
        range_data=dict(raw.get("range", {}))
        if isinstance(raw.get("range"), dict)
        else {},
        duration_data=tuple(
            entry for entry in raw.get("duration", []) if isinstance(entry, dict)
        ),
        components=(
            dict(raw.get("components", {}))
            if isinstance(raw.get("components"), dict)
            else {}
        ),
        saving_throw_abilities=tuple(
            ability
            for value in raw.get("savingThrow", [])
            if (ability := _normalize_save_ability(value)) is not None
        ),
        condition_inflict=tuple(
            value for value in raw.get("conditionInflict", []) if isinstance(value, str)
        ),
        removable_conditions=_spell_removable_conditions(raw),
        damage_dice=_spell_damage_dice(raw),
        damage_inflict=tuple(
            value for value in raw.get("damageInflict", []) if isinstance(value, str)
        ),
        area_tags=tuple(
            value for value in raw.get("areaTags", []) if isinstance(value, str)
        ),
        geometry_mode=_spell_geometry_mode(raw),
        area_size_feet=_spell_area_size_feet(raw),
    )


def _normalize_save_ability(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    aliases = {
        "str": "strength",
        "dex": "dexterity",
        "con": "constitution",
        "int": "intelligence",
        "wis": "wisdom",
        "cha": "charisma",
    }
    normalized = value.casefold()
    return aliases.get(normalized, normalized)


def _spell_damage_dice(raw: dict[str, object]) -> str | None:
    entries = raw.get("entries", [])
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, str):
            continue
        match = re.search(r"\{@damage ([^}]+)\}", entry)
        if match is not None:
            return match.group(1)
    return None


def _spell_removable_conditions(raw: dict) -> tuple[str, ...]:
    entries = raw.get("entries", [])
    if not isinstance(entries, list):
        return ()
    text_parts = [entry for entry in entries if isinstance(entry, str)]
    if not text_parts:
        return ()
    text = " ".join(text_parts)
    if "end one condition on it:" not in text.casefold():
        return ()
    return tuple(
        match.casefold() for match in re.findall(r"\{@condition ([^|}]+)", text)
    )


def _spell_geometry_mode(raw: dict) -> str:
    range_data = raw.get("range", {})
    range_type = (
        range_data.get("type")
        if isinstance(range_data, dict) and isinstance(range_data.get("type"), str)
        else None
    )
    removable_conditions = _spell_removable_conditions(raw)
    area_tags = tuple(
        value for value in raw.get("areaTags", []) if isinstance(value, str)
    )

    if removable_conditions and range_type == "point":
        return "self_only"
    if range_type in {"cone", "line", "cube"}:
        return "directional_area"
    if range_type in {"radius", "sphere", "cylinder", "emanation"}:
        return "non_directional_area"
    if range_type == "point" and area_tags:
        return "point_area"
    return "point_target"


def _spell_area_size_feet(raw: dict[str, object]) -> int | None:
    entries = raw.get("entries", [])
    if not isinstance(entries, list):
        return None
    text_parts = [entry for entry in entries if isinstance(entry, str)]
    if not text_parts:
        return None
    text = " ".join(text_parts).casefold()
    radius_match = re.search(r"(\d+)-foot-radius", text)
    if radius_match is not None:
        return int(radius_match.group(1))
    return None


def _second_wind_uses(class_block: dict | None, feature_level: int) -> int:
    if class_block is None:
        return 1
    source = class_block.get("source")
    if source != "XPHB":
        return 1
    table_value = _class_table_value(class_block, "Second Wind", feature_level)
    if table_value is None:
        return 2
    try:
        return int(table_value)
    except ValueError:
        return 2


def _action_surge_uses(class_block: dict | None, feature_level: int) -> int:
    if class_block is None:
        return 1
    table_value = _class_table_value(class_block, "Action Surge", feature_level)
    if table_value is None:
        return 1
    try:
        return int(table_value)
    except ValueError:
        return 1


def _second_wind_healing_dice(
    class_block: dict | None,
    feature_name: str,
    feature_level: int,
) -> dict[str, int]:
    feature_entry = _class_feature_entry(class_block, feature_name, feature_level)
    dice = _first_dice_expression(feature_entry)
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
    class_block: dict | None,
    feature_name: str,
    feature_level: int,
) -> dict | None:
    if class_block is None:
        return None
    class_name = class_block.get("name")
    class_source = class_block.get("source")
    entries = class_block.get("__classFeatureEntries", [])
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("name") != feature_name or entry.get("level") != feature_level:
            continue
        if entry.get("className") != class_name:
            continue
        if entry.get("classSource") != class_source:
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
    class_block: dict,
    column_label: str,
    level: int,
) -> str | None:
    groups = class_block.get("classTableGroups", [])
    if not isinstance(groups, list):
        return None
    for group in groups:
        if not isinstance(group, dict):
            continue
        labels = group.get("colLabels", [])
        rows = group.get("rows", [])
        if not isinstance(labels, list) or not isinstance(rows, list):
            continue
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


def _stat_block_name(stat_block: dict | None) -> str:
    if stat_block is None:
        raise ValueError("Creature must define either 'name' or 'stat_block'.")
    return str(stat_block["name"])
