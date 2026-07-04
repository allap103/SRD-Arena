from pathlib import Path
import re
from typing import cast

from ..schemas import ActorSchema
from ..schemas.actor import ActorItemReferenceSchema
from ...models.actor import Actor
from ...models.attributes import Attributes, Movement
from ...models.class_features import (
    ClassRef,
    CombatProfile,
    FeatureActionDefinition,
    FeatureGrant,
    SubclassRef,
)
from ...models.monster_attack import MonsterAttack
from ...models.spellcasting import Spell, Spellcasting
from ...rules.normalization import normalize_optional_feature_rules
from ...rules.types import RuleGrant
from ...systems.equipment import Equipment
from ...systems.inventory import Inventory
from ._catalogs import (
    _find_class_block,
    _find_optional_feature,
    _find_spell,
    _find_stat_block,
    _find_subclass_block,
)
from ._shared import _load_json, _slug
from ._types import (
    ClassCatalog,
    CustomStatBlockCatalog,
    OptionalFeatureCatalog,
    SpellCatalog,
    StatBlockCatalog,
    SubclassCatalog,
)


def load_actor(
    path: str | Path,
    stat_blocks: StatBlockCatalog | None = None,
    class_blocks: ClassCatalog | None = None,
    custom_stat_blocks: CustomStatBlockCatalog | None = None,
    optional_features: OptionalFeatureCatalog | None = None,
    subclass_blocks: SubclassCatalog | None = None,
    spell_catalog: SpellCatalog | None = None,
) -> Actor:
    schema = _resolve_actor_schema(
        ActorSchema.model_validate(_load_json(path)),
        custom_stat_blocks,
    )
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
                slot: _actor_item_id(item)
                for slot, item in cast(dict[str, object], dict(schema.equipment)).items()
            },
        }
    )
    attributes = _build_actor_attributes(schema, stat_block, class_block)
    feature_grants = _resolve_class_feature_grants(class_block, schema.attributes.level)
    feature_grants.extend(
        _resolve_subclass_feature_grants(
            subclass_block,
            schema.attributes.level,
            class_name=schema.class_ref.name if schema.class_ref else None,
        )
    )
    rule_grants = _resolve_optional_feature_rules(schema, optional_features)
    combat_profile = _build_combat_profile(feature_grants)
    spellcasting = _build_spellcasting(
        schema,
        attributes,
        class_block,
        subclass_block,
        spell_catalog,
    )

    return Actor(
        id=schema.id,
        name=schema.name or _stat_block_name(stat_block),
        description=schema.description,
        inventory=Inventory(items=[_actor_item_id(item) for item in schema.inventory]),
        attributes=attributes,
        equipment=equipment,
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
        feature_grants=feature_grants,
        rule_grants=rule_grants,
        combat_profile=combat_profile,
        feature_uses_remaining=_build_feature_uses_remaining(combat_profile),
        monster_attacks=_build_monster_attacks(stat_block),
        spellcasting=spellcasting,
    )


def _resolve_actor_schema(
    instance: ActorSchema,
    custom_stat_blocks: CustomStatBlockCatalog | None,
) -> ActorSchema:
    if instance.custom_stat_block is None:
        return instance
    if custom_stat_blocks is None:
        raise ValueError(
            f"Actor '{instance.id}' references custom stat block "
            f"'{instance.custom_stat_block}', but no custom stat block catalog was loaded."
        )
    template = custom_stat_blocks.get(instance.custom_stat_block)
    if template is None:
        raise KeyError(f"Custom stat block '{instance.custom_stat_block}' not found.")

    template_data = template.model_dump(exclude={"id", "custom_stat_block"})
    instance_data = instance.model_dump(
        exclude_unset=True,
        exclude={
            "attributes",
            "custom_stat_block",
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
    return ActorSchema.model_validate(merged)


def _resolve_optional_feature_rules(
    schema: ActorSchema,
    catalog: OptionalFeatureCatalog | None,
) -> list[RuleGrant]:
    rules: list[RuleGrant] = []
    for reference in schema.optional_features:
        if catalog is None:
            raise ValueError(
                f"Actor references optional feature '{reference.name}', "
                "but no optional feature catalog was loaded."
            )
        feature = _find_optional_feature(reference.name, reference.source, catalog)
        rules.extend(normalize_optional_feature_rules(feature))
    return rules


def _actor_item_id(item: str | ActorItemReferenceSchema | object) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, ActorItemReferenceSchema):
        return _slug(item.name)
    if isinstance(item, dict):
        name = item.get("name")
        if isinstance(name, str):
            return _slug(name)
    raise TypeError(f"Unsupported actor item reference: {item!r}")


def _build_actor_attributes(
    schema: ActorSchema,
    stat_block: dict | None,
    class_block: dict | None,
) -> Attributes:
    if stat_block is None:
        attributes = schema.attributes.model_dump(exclude={"movement"})
        attributes["proficiencies"] = _merge_proficiencies(
            schema.attributes.proficiencies,
            _class_proficiencies(class_block),
        )
        return Attributes(
            **attributes,
            movement=Movement(**schema.attributes.movement.model_dump()),
        )

    proficiencies = _merge_proficiencies(
        schema.attributes.proficiencies,
        _class_proficiencies(class_block),
    )
    return Attributes(
        base_health=int(stat_block.get("hp", {}).get("average", schema.attributes.base_health)),
        level=schema.attributes.level,
        movement=Movement(
            speed_feet=int(stat_block.get("speed", {}).get("walk", schema.attributes.movement.speed_feet)),
            feet_per_square=schema.attributes.movement.feet_per_square,
        ),
        strength=int(stat_block.get("str", schema.attributes.strength)),
        dexterity=int(stat_block.get("dex", schema.attributes.dexterity)),
        constitution=int(stat_block.get("con", schema.attributes.constitution)),
        wisdom=int(stat_block.get("wis", schema.attributes.wisdom)),
        intelligence=int(stat_block.get("int", schema.attributes.intelligence)),
        charisma=int(stat_block.get("cha", schema.attributes.charisma)),
        base_armor_class=_stat_block_base_ac(stat_block, schema.attributes.base_armor_class),
        proficiencies=proficiencies,
    )


def _merge_proficiencies(*sources: dict[str, object]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for source in sources:
        for key, value in source.items():
            if isinstance(value, list):
                existing = merged.setdefault(key, [])
                if isinstance(existing, list):
                    existing.extend(item for item in value if item not in existing)
                continue
            merged[key] = value
    return merged


def _class_proficiencies(class_block: dict | None) -> dict[str, object]:
    if class_block is None:
        return {}
    starting = class_block.get("startingProficiencies", {})
    weapons = starting.get("weapons", []) if isinstance(starting, dict) else []
    proficiencies: dict[str, object] = {}
    if isinstance(weapons, list):
        proficiencies["weapons"] = list(weapons)

    saving_throws = class_block.get("proficiency", [])
    if isinstance(saving_throws, list):
        ability_names = {
            "str": "strength",
            "dex": "dexterity",
            "con": "constitution",
            "int": "intelligence",
            "wis": "wisdom",
            "cha": "charisma",
        }
        proficiencies["saving_throws"] = [
            ability_names.get(str(ability).casefold(), str(ability).casefold())
            for ability in saving_throws
        ]
    return proficiencies


def _resolve_class_feature_grants(
    class_block: dict | None,
    level: int,
) -> list[FeatureGrant]:
    if class_block is None:
        return []

    class_name = str(class_block.get("name", ""))
    features = class_block.get("classFeatures", [])
    grants: list[FeatureGrant] = []
    if not isinstance(features, list):
        return grants

    for feature_ref in features:
        parsed = _parse_class_feature_reference(feature_ref)
        if parsed is None:
            continue
        feature_name, feature_level = parsed
        if feature_level > level:
            continue
        grant = _normalize_feature_grant(
            class_name,
            feature_name,
            feature_level,
            class_block,
            level,
        )
        if grant is not None:
            grants.append(grant)
    return grants


def _resolve_subclass_feature_grants(
    subclass_block: dict | None,
    level: int,
    *,
    class_name: str | None,
) -> list[FeatureGrant]:
    if subclass_block is None:
        return []

    subclass_name = str(subclass_block.get("name", ""))
    features = subclass_block.get("subclassFeatures", [])
    grants: list[FeatureGrant] = []
    if not isinstance(features, list):
        return grants

    for feature_ref in features:
        parsed = _parse_class_feature_reference(feature_ref)
        if parsed is None:
            continue
        feature_name, feature_level = parsed
        if feature_level > level:
            continue
        grant = _normalize_feature_grant(
            class_name or str(subclass_block.get("className", "")),
            feature_name,
            feature_level,
            source_subclass=subclass_name,
        )
        if grant is not None:
            grants.append(grant)
    return grants


def _parse_class_feature_reference(feature_ref: str | dict[str, object]) -> tuple[str, int] | None:
    raw_ref = feature_ref if isinstance(feature_ref, str) else feature_ref.get("classFeature")
    if not isinstance(raw_ref, str):
        return None
    parts = raw_ref.split("|")
    if not parts:
        return None
    for part in reversed(parts):
        if part.isdigit():
            return (parts[0], int(part))
    return None


def _normalize_feature_grant(
    class_name: str,
    feature_name: str,
    feature_level: int,
    class_block: dict | None = None,
    actor_level: int = 1,
    source_subclass: str | None = None,
) -> FeatureGrant | None:
    extra_attack_counts = {
        "Extra Attack": 2,
        "Extra Attack (2)": 3,
        "Extra Attack (3)": 4,
        "Extra Attack Improvement": 2,
    }
    attacks = extra_attack_counts.get(feature_name)
    if attacks is None:
        if feature_name == "Second Wind":
            return FeatureGrant(
                id="second_wind",
                name=feature_name,
                source_class=class_name,
                level=feature_level,
                source_subclass=source_subclass,
                data={
                    "uses": _second_wind_uses(class_block, actor_level),
                    **_second_wind_healing_dice(class_block, feature_name, feature_level),
                },
            )
        if feature_name == "Action Surge":
            return FeatureGrant(
                id="action_surge",
                name=feature_name,
                source_class=class_name,
                level=feature_level,
                source_subclass=source_subclass,
                data={"uses": _action_surge_uses(class_block, actor_level)},
            )
        else:
            return None
    return FeatureGrant(
        id="extra_attack",
        name=feature_name,
        source_class=class_name,
        level=feature_level,
        source_subclass=source_subclass,
        data={"attacks": attacks},
    )


def _build_combat_profile(feature_grants: list[FeatureGrant]) -> CombatProfile:
    profile = CombatProfile()
    for grant in feature_grants:
        if grant.id == "extra_attack":
            attacks = grant.data.get("attacks")
            if isinstance(attacks, int):
                profile.attacks_per_attack_action = max(
                    profile.attacks_per_attack_action,
                    attacks,
                )
            continue
        if grant.id == "second_wind":
            profile.bonus_action_options.add("second_wind")
            profile.feature_actions["second_wind"] = FeatureActionDefinition(
                feature_id="second_wind",
                label="Second Wind",
                economy="bonus_action",
                target="self",
                resolver="second_wind",
            )
            uses = grant.data.get("uses")
            if isinstance(uses, int):
                profile.feature_uses_max["second_wind"] = max(
                    profile.feature_uses_max.get("second_wind", 0),
                    uses,
                )
            if grant.source_class == "Fighter" and grant.name == "Second Wind":
                if uses == 1:
                    profile.feature_recharge["second_wind"] = {
                        "short_rest": "all",
                        "long_rest": "all",
                    }
                else:
                    profile.feature_recharge["second_wind"] = {
                        "short_rest": 1,
                        "long_rest": "all",
                    }
            continue
        if grant.id == "action_surge":
            profile.feature_actions["action_surge"] = FeatureActionDefinition(
                feature_id="action_surge",
                label="Action Surge",
                economy="none",
                target="self",
                resolver="action_surge",
            )
            uses = grant.data.get("uses")
            if isinstance(uses, int):
                profile.feature_uses_max["action_surge"] = max(
                    profile.feature_uses_max.get("action_surge", 0),
                    uses,
                )
            profile.feature_recharge["action_surge"] = {
                "short_rest": "all",
                "long_rest": "all",
            }
    return profile


def _build_feature_uses_remaining(combat_profile: CombatProfile) -> dict[str, int]:
    return dict(combat_profile.feature_uses_max)


def _build_spellcasting(
    schema: ActorSchema,
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
        cantrips_known=_progression_value(source_block.get("cantripProgression"), level) or 0,
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


def _spellcasting_ability_score(attributes: Attributes, ability: str) -> int:
    ability_map = {
        "str": attributes.strength,
        "dex": attributes.dexterity,
        "con": attributes.constitution,
        "int": attributes.intelligence,
        "wis": attributes.wisdom,
        "cha": attributes.charisma,
    }
    return ability_map.get(ability.casefold(), 10)


def _spell_preparation_mode(block: dict) -> str:
    groups = block.get("subclassTableGroups") or block.get("classTableGroups") or []
    if not isinstance(groups, list):
        return "fixed"
    for group in groups:
        if not isinstance(group, dict):
            continue
        labels = group.get("colLabels")
        if not isinstance(labels, list):
            continue
        if any(isinstance(label, str) and "Spells Prepared" in label for label in labels):
            return "fixed"
        if any(isinstance(label, str) and "Spells Known" in label for label in labels):
            return "fixed"
    return "fixed"


def _progression_value(progression: object, level: int) -> int | None:
    if not isinstance(progression, list):
        return None
    row_index = level - 1
    if row_index < 0 or row_index >= len(progression):
        return None
    value = progression[row_index]
    return int(value) if isinstance(value, int) else None


def _spell_slots_progression(block: dict, level: int) -> dict[int, int]:
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
        if not isinstance(row, list):
            continue
        return {
            spell_level: slots
            for spell_level, slots in enumerate(row, start=1)
            if isinstance(slots, int) and slots > 0
        }
    return {}


def _spell_count_progression(block: dict, level: int) -> int | None:
    direct = _progression_value(block.get("spellsKnownProgression"), level)
    if direct is not None:
        return direct

    groups = block.get("subclassTableGroups") or block.get("classTableGroups") or []
    if not isinstance(groups, list):
        return None
    row_index = level - 1
    for group in groups:
        if not isinstance(group, dict):
            continue
        labels = group.get("colLabels")
        rows = group.get("rows")
        if not isinstance(labels, list) or not isinstance(rows, list):
            continue
        if not any(
            isinstance(label, str)
            and ("Spells Known" in label or "Spells Prepared" in label)
            for label in labels
        ):
            continue
        if row_index < 0 or row_index >= len(rows):
            continue
        row = rows[row_index]
        if not isinstance(row, list) or not row:
            continue
        value = row[0]
        return int(value) if isinstance(value, int) else None
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
        range_data=dict(raw.get("range", {})) if isinstance(raw.get("range"), dict) else {},
        duration_data=tuple(
            entry for entry in raw.get("duration", []) if isinstance(entry, dict)
        ),
        components=(
            dict(raw.get("components", {}))
            if isinstance(raw.get("components"), dict)
            else {}
        ),
        saving_throw_abilities=tuple(
            _normalize_save_ability(value)
            for value in raw.get("savingThrow", [])
            if _normalize_save_ability(value) is not None
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
        match.casefold()
        for match in re.findall(r"\{@condition ([^|}]+)", text)
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
        raise ValueError("Actor must define either 'name' or 'stat_block'.")
    return str(stat_block["name"])


def _build_monster_attacks(stat_block: dict | None) -> list[MonsterAttack]:
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
    range_normal = int(range_match.group(1)) if range_match is not None else None
    range_long = int(range_match.group(2)) if range_match is not None else None

    return MonsterAttack(
        name=name,
        attack_modes=attack_modes,
        attack_bonus=int(hit.group(1)),
        damage_dice=damage.group(1),
        damage_bonus=int(damage.group(2) or 0),
        damage_type=damage_type.group(1).lower(),
        range_normal=range_normal,
        range_long=range_long,
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


def _stat_block_base_ac(stat_block: dict, default: int) -> int:
    armor_class = _stat_block_ac(stat_block, default)
    dexterity = int(stat_block.get("dex", 10))
    return armor_class - ((dexterity - 10) // 2)


def _stat_block_ac(stat_block: dict, default: int) -> int:
    ac = stat_block.get("ac")
    if not isinstance(ac, list) or not ac:
        return default
    first = ac[0]
    if isinstance(first, int):
        return first
    if isinstance(first, dict) and isinstance(first.get("ac"), int):
        return first["ac"]
    return default
