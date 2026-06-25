import json
from pathlib import Path
from typing import cast

from .content_schema import ActorSchema, ItemSchema, SceneSchema
from .content_schema.actor import ActorItemReferenceSchema
from .models.actor import Actor
from .models.attributes import Attributes, Movement
from .models.class_features import (
    ClassRef,
    CombatProfile,
    FeatureActionDefinition,
    FeatureGrant,
)
from .models.choice import (
    Choice,
    Effects,
    ItemRequirement,
    Outcome,
    Requirements,
    SkillTest,
)
from .models.item import ArmorStat, Item, WeaponStat
from .models.scene import (
    Behavior,
    Encounter,
    EncounterEnemy,
    EncounterResolution,
    FleeResolution,
    Grid,
    Position,
    Scene,
)
from .systems.equipment import Equipment
from .systems.inventory import Inventory


StatBlockCatalog = dict[tuple[str, str | None], dict]
ClassCatalog = dict[tuple[str, str | None], dict]
CustomStatBlockCatalog = dict[str, ActorSchema]
SystemItemCatalog = dict[tuple[str, str | None], dict]
SOURCE_PRIORITY = {
    "XPHB": 30,
    "XDMG": 30,
    "PHB": 20,
    "DMG": 20,
}


def _load_json(path: str | Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def _build_requirements(requirements) -> Requirements | None:
    if requirements is None:
        return None

    return Requirements(
        items=[
            ItemRequirement(
                id=item.id,
                quantity=item.quantity,
                missing_message=item.missing_message,
                consume=item.consume,
            )
            for item in requirements.items
        ]
    )


def _build_effects(effects) -> Effects | None:
    if effects is None:
        return None

    def build_outcome(outcome) -> Outcome | None:
        if outcome is None:
            return None
        return Outcome(
            message=outcome.message,
            next_scene=outcome.next_scene,
            gain_item=outcome.gain_item,
            lose_item=outcome.lose_item,
            damage=outcome.damage,
            healing=outcome.healing,
        )

    return Effects(
        on_success=build_outcome(effects.on_success),
        on_failure=build_outcome(effects.on_failure),
    )


def _build_test(test) -> SkillTest | None:
    if test is None:
        return None

    return SkillTest(
        skill=test.skill,
        difficulty=test.difficulty,
        repeatable=test.repeatable,
        effects=_build_effects(test.effects),
    )


def _build_position(position) -> Position:
    return Position(x=position.x, y=position.y)


def _build_encounter(encounter) -> Encounter | None:
    if encounter is None:
        return None

    return Encounter(
        grid=Grid(width=encounter.grid.width, height=encounter.grid.height),
        player_start=_build_position(encounter.player_start),
        enemies=[
            EncounterEnemy(
                actor_id=enemy.actor_id,
                start=_build_position(enemy.start),
                behavior=Behavior(
                    type=enemy.behavior.type,
                    anchor=_build_position(enemy.behavior.anchor)
                    if enemy.behavior.anchor
                    else None,
                    radius=enemy.behavior.radius,
                    path=[
                        _build_position(path_position)
                        for path_position in enemy.behavior.path
                    ],
                ),
            )
            for enemy in encounter.enemies
        ],
        victory=EncounterResolution(next_scene=encounter.victory.next_scene),
        defeat=EncounterResolution(next_scene=encounter.defeat.next_scene),
        flee=FleeResolution(
            next_scene=encounter.flee.next_scene,
            allowed=encounter.flee.allowed,
        )
        if encounter.flee
        else None,
    )


def load_actor(
    path: str | Path,
    stat_blocks: StatBlockCatalog | None = None,
    class_blocks: ClassCatalog | None = None,
    custom_stat_blocks: CustomStatBlockCatalog | None = None,
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
    equipment = Equipment(
        equipped_items={
            **Equipment().equipped_items,
            **{
                slot: _actor_item_id(item)
                for slot, item in cast(dict[str, object], dict(schema.equipment)).items()
            },
        }
    )
    feature_grants = _resolve_class_feature_grants(class_block, schema.attributes.level)
    combat_profile = _build_combat_profile(feature_grants)

    return Actor(
        id=schema.id,
        name=schema.name or _stat_block_name(stat_block),
        description=schema.description,
        inventory=Inventory(items=[_actor_item_id(item) for item in schema.inventory]),
        attributes=_build_actor_attributes(schema, stat_block, class_block),
        equipment=equipment,
        class_ref=(
            ClassRef(name=schema.class_ref.name, source=schema.class_ref.source)
            if schema.class_ref
            else None
        ),
        feature_grants=feature_grants,
        combat_profile=combat_profile,
        feature_uses_remaining=_build_feature_uses_remaining(combat_profile),
    )


def load_custom_stat_blocks(directory: str | Path) -> CustomStatBlockCatalog:
    custom_dir = Path(directory)
    if not custom_dir.is_dir():
        return {}
    return {
        schema.id: schema
        for schema in (ActorSchema.model_validate(_load_json(path)) for path in custom_dir.glob("*"))
    }


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
    }
    return ActorSchema.model_validate(merged)


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


def load_bestiary_stat_blocks(directory: str | Path) -> StatBlockCatalog:
    catalog: StatBlockCatalog = {}
    bestiary_dir = Path(directory) / "bestiary"
    if not bestiary_dir.is_dir():
        return catalog

    for path in bestiary_dir.glob("bestiary-*.json"):
        data = _load_json(path)
        for monster in data.get("monster", []):
            if not isinstance(monster, dict) or not isinstance(monster.get("name"), str):
                continue
            source = monster.get("source")
            source_key = source if isinstance(source, str) else None
            catalog[(monster["name"].casefold(), source_key)] = monster
            catalog.setdefault((monster["name"].casefold(), None), monster)
    return catalog


def load_class_blocks(directory: str | Path) -> ClassCatalog:
    catalog: ClassCatalog = {}
    class_dir = Path(directory) / "class"
    if not class_dir.is_dir():
        return catalog

    for path in class_dir.glob("class-*.json"):
        data = _load_json(path)
        for class_block in data.get("class", []):
            if not isinstance(class_block, dict) or not isinstance(class_block.get("name"), str):
                continue
            source = class_block.get("source")
            source_key = source if isinstance(source, str) else None
            catalog[(class_block["name"].casefold(), source_key)] = class_block
            catalog.setdefault((class_block["name"].casefold(), None), class_block)
    return catalog


def load_system_items(directory: str | Path) -> list[Item]:
    catalog = load_system_item_catalog(directory)
    items_by_id: dict[str, tuple[int, Item]] = {}
    for raw_item in catalog.values():
        item = _build_system_item(raw_item)
        priority = SOURCE_PRIORITY.get(str(raw_item.get("source", "")), 0)
        current = items_by_id.get(item.id)
        if current is None or priority >= current[0]:
            items_by_id[item.id] = (priority, item)
    return [item for _, item in items_by_id.values()]


def load_system_item_catalog(directory: str | Path) -> SystemItemCatalog:
    system_dir = Path(directory)
    catalog: SystemItemCatalog = {}
    for path, key in ((system_dir / "items-base.json", "baseitem"), (system_dir / "items.json", "item")):
        if not path.is_file():
            continue
        data = _load_json(path)
        for raw_item in data.get(key, []):
            if not isinstance(raw_item, dict) or not isinstance(raw_item.get("name"), str):
                continue
            source = raw_item.get("source")
            source_key = source if isinstance(source, str) else None
            catalog[(raw_item["name"].casefold(), source_key)] = raw_item
            fallback_key = (raw_item["name"].casefold(), None)
            current = catalog.get(fallback_key)
            if current is None or SOURCE_PRIORITY.get(str(source), 0) >= SOURCE_PRIORITY.get(str(current.get("source", "")), 0):
                catalog[fallback_key] = raw_item
    return catalog


def _find_stat_block(
    name: str,
    source: str | None,
    stat_blocks: StatBlockCatalog | None,
) -> dict:
    if stat_blocks is None:
        raise ValueError(f"Actor references stat block '{name}', but no stat block catalog was loaded.")
    key = (name.casefold(), source)
    if key in stat_blocks:
        return stat_blocks[key]
    if source is not None:
        source_key = (name.casefold(), source.upper())
        if source_key in stat_blocks:
            return stat_blocks[source_key]
    fallback_key = (name.casefold(), None)
    if source is None and fallback_key in stat_blocks:
        return stat_blocks[fallback_key]
    source_text = f"|{source}" if source else ""
    raise KeyError(f"Stat block '{name}{source_text}' not found.")


def _find_class_block(
    name: str,
    source: str | None,
    class_blocks: ClassCatalog | None,
) -> dict:
    if class_blocks is None:
        raise ValueError(f"Actor references class '{name}', but no class catalog was loaded.")
    key = (name.casefold(), source)
    if key in class_blocks:
        return class_blocks[key]
    if source is not None:
        source_key = (name.casefold(), source.upper())
        if source_key in class_blocks:
            return class_blocks[source_key]
    fallback_key = (name.casefold(), None)
    if source is None and fallback_key in class_blocks:
        return class_blocks[fallback_key]
    source_text = f"|{source}" if source else ""
    raise KeyError(f"Class '{name}{source_text}' not found.")


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
    return {"weapons": list(weapons)} if isinstance(weapons, list) else {}


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
) -> FeatureGrant | None:
    extra_attack_counts = {
        "Extra Attack": 2,
        "Extra Attack (2)": 3,
        "Extra Attack (3)": 4,
        "Extra Attack Improvement": 2,
    }
    attacks = extra_attack_counts.get(feature_name)
    if attacks is None:
        if feature_name != "Second Wind":
            return None
        return FeatureGrant(
            id="second_wind",
            name=feature_name,
            source_class=class_name,
            level=feature_level,
            data={
                "uses": _second_wind_uses(class_block, actor_level),
                "healing_die_count": 1,
                "healing_die_sides": 10,
            },
        )
    return FeatureGrant(
        id="extra_attack",
        name=feature_name,
        source_class=class_name,
        level=feature_level,
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
    return profile


def _build_feature_uses_remaining(combat_profile: CombatProfile) -> dict[str, int]:
    return dict(combat_profile.feature_uses_max)


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


def _build_system_item(raw_item: dict) -> Item:
    item_id = _slug(str(raw_item["name"]))
    item_type = str(raw_item.get("type", ""))
    if raw_item.get("weapon") or raw_item.get("dmg1"):
        return Item(
            id=item_id,
            name=str(raw_item["name"]),
            description=_system_item_description(raw_item),
            category="weapon",
            weapon_stat=WeaponStat(
                slot=["left_hand", "right_hand"],
                damage=str(raw_item.get("dmg1", "1d4")),
                damage_type=_damage_type(str(raw_item.get("dmgType", ""))),
                properties=[_property_name(str(prop)) for prop in raw_item.get("property", [])],
                weapon_category=str(raw_item.get("weaponCategory", "")),
            ),
            item_type=item_type,
            misc_tags=_misc_tags(raw_item),
        )
    if raw_item.get("armor") or isinstance(raw_item.get("ac"), int):
        return Item(
            id=item_id,
            name=str(raw_item["name"]),
            description=_system_item_description(raw_item),
            category="armor",
            armor_stat=ArmorStat(
                slot="body",
                type=_armor_type(item_type),
                armor_class=int(raw_item.get("ac", 10)),
                modifier_cap=0 if item_type.startswith("HA") else 2 if item_type.startswith("MA") else 99,
            ),
            item_type=item_type,
            misc_tags=_misc_tags(raw_item),
        )
    return Item(
        id=item_id,
        name=str(raw_item["name"]),
        description=_system_item_description(raw_item),
        category="other",
        item_type=item_type,
        misc_tags=_misc_tags(raw_item),
    )


def _system_item_description(raw_item: dict) -> str:
    entries = raw_item.get("entries", [])
    if entries and isinstance(entries[0], str):
        return entries[0]
    return ""


def _slug(value: str) -> str:
    return value.lower().replace("'", "").replace(",", "").replace(" ", "_")


def _armor_type(item_type: str) -> str:
    if item_type.startswith("HA"):
        return "heavy"
    if item_type.startswith("MA"):
        return "medium"
    if item_type.startswith("LA"):
        return "light"
    return "armor"


def _damage_type(value: str) -> str:
    return {
        "B": "bludgeoning",
        "P": "piercing",
        "S": "slashing",
    }.get(value, value.lower() or "damage")


def _property_name(value: str) -> str:
    return {
        "V": "versatile",
        "F": "finesse",
        "L": "light",
        "T": "thrown",
    }.get(value.split("|", 1)[0], value.lower())


def load_item(path: str | Path, system_items: SystemItemCatalog | None = None) -> Item:
    schema = ItemSchema.model_validate(_load_json(path))
    if schema.item_ref is not None:
        if system_items is None:
            raise ValueError(f"Item '{schema.id}' references a system item, but no system item catalog was loaded.")
        raw_item = _find_system_item(schema.item_ref.name, schema.item_ref.source, system_items)
        item = _build_system_item(raw_item)
        item.id = schema.id
        if schema.name is not None:
            item.name = schema.name
        if schema.description:
            item.description = schema.description
        return item

    assert schema.name is not None
    assert schema.category is not None
    return Item(
        id=schema.id,
        name=schema.name,
        description=schema.description,
        category=schema.category,
        weapon_stat=WeaponStat(**schema.weapon_stat.model_dump())
        if schema.weapon_stat
        else None,
        armor_stat=ArmorStat(**schema.armor_stat.model_dump())
        if schema.armor_stat
        else None,
        item_type=schema.item_type,
        misc_tags=list(schema.misc_tags),
    )


def _misc_tags(raw_item: dict) -> list[str]:
    tags = raw_item.get("miscTags", [])
    if not isinstance(tags, list):
        return []
    return [str(tag) for tag in tags]


def _find_system_item(
    name: str,
    source: str | None,
    system_items: SystemItemCatalog,
) -> dict:
    key = (name.casefold(), source)
    if key in system_items:
        return system_items[key]
    if source is not None:
        source_key = (name.casefold(), source.upper())
        if source_key in system_items:
            return system_items[source_key]
    fallback_key = (name.casefold(), None)
    if source is None and fallback_key in system_items:
        return system_items[fallback_key]
    source_text = f"|{source}" if source else ""
    raise KeyError(f"System item '{name}{source_text}' not found.")


def load_scene(path: str | Path) -> Scene:
    schema = SceneSchema.model_validate(_load_json(path))
    choices = [
        Choice(
            choice_text=choice_text,
            next_scene=choice.next_scene,
            message=choice.message,
            requirements=_build_requirements(choice.requirements),
            test=_build_test(choice.test),
        )
        for choice_text, choice in schema.choices.items()
    ]
    return Scene(
        id=schema.id,
        type=schema.type,
        text=schema.text,
        choices=choices,
        encounter=_build_encounter(schema.encounter),
    )
