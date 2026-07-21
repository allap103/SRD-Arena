from pathlib import Path

from ..schemas import ItemSchema
from ...domain.item import ArmorStat, Item, WeaponStat
from .catalogs import _find_system_item, load_system_item_catalog
from .source_data import SOURCE_PRIORITY, _load_json, _slug
from .types import SystemItemCatalog


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


def _build_system_item(raw_item: dict) -> Item:
    item_id = _slug(str(raw_item["name"]))
    item_type = str(raw_item.get("type", ""))
    if raw_item.get("weapon") or raw_item.get("dmg1"):
        return Item(
            id=item_id,
            name=str(raw_item["name"]),
            description=_system_item_description(raw_item),
            category="weapon",
            weapon_stat=_build_weapon_stat(
                slot=["left_hand", "right_hand"],
                damage=str(raw_item.get("dmg1", "1d4")),
                damage_type=_damage_type(str(raw_item.get("dmgType", ""))),
                properties=[_property_name(str(prop)) for prop in raw_item.get("property", [])],
                attack_type=_attack_type(item_type),
                range_normal=_weapon_range(raw_item)[0],
                range_long=_weapon_range(raw_item)[1],
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
            armor_stat=_build_armor_stat(
                slot="body",
                type=_armor_type(item_type),
                armor_class=int(raw_item.get("ac", 10)),
                modifier_cap=0
                if item_type.startswith("HA")
                else 2
                if item_type.startswith("MA")
                else 99,
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


def _armor_type(item_type: str) -> str:
    if item_type.startswith("HA"):
        return "heavy"
    if item_type.startswith("MA"):
        return "medium"
    if item_type.startswith("LA"):
        return "light"
    return "armor"


def _attack_type(item_type: str) -> str:
    base_type = item_type.split("|", 1)[0]
    if base_type == "R":
        return "ranged"
    if base_type == "M":
        return "melee"
    return ""


def _weapon_range(raw_item: dict) -> tuple[int | None, int | None]:
    raw_range = raw_item.get("range")
    if not isinstance(raw_range, str):
        return None, None
    parts = raw_range.split("/", 1)
    try:
        normal = int(parts[0])
    except ValueError:
        return None, None
    if len(parts) == 1:
        return normal, None
    try:
        return normal, int(parts[1])
    except ValueError:
        return normal, None


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
        "H": "heavy",
        "L": "light",
        "T": "thrown",
        "2H": "two-handed",
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
        weapon_stat=_build_weapon_stat_from_schema(schema.weapon_stat),
        armor_stat=_build_armor_stat_from_schema(schema.armor_stat),
        item_type=schema.item_type,
        misc_tags=list(schema.misc_tags),
    )


def _build_weapon_stat_from_schema(schema: object) -> WeaponStat | None:
    if schema is None:
        return None
    return _build_weapon_stat(**schema.model_dump())


def _build_armor_stat_from_schema(schema: object) -> ArmorStat | None:
    if schema is None:
        return None
    return _build_armor_stat(**schema.model_dump())


def _build_weapon_stat(
    *,
    slot: list[str],
    damage: str,
    damage_type: str,
    properties: list[str],
    attack_type: str = "",
    range_normal: int | None = None,
    range_long: int | None = None,
    weapon_category: str = "",
) -> WeaponStat:
    return WeaponStat(
        slot=slot,
        damage=damage,
        damage_type=damage_type,
        properties=properties,
        attack_type=attack_type,
        range_normal=range_normal,
        range_long=range_long,
        weapon_category=weapon_category,
    )


def _build_armor_stat(
    *,
    slot: str,
    type: str,
    armor_class: int,
    modifier_cap: int,
) -> ArmorStat:
    return ArmorStat(
        slot=slot,
        type=type,
        armor_class=armor_class,
        modifier_cap=modifier_cap,
    )


def _misc_tags(raw_item: dict) -> list[str]:
    tags = raw_item.get("miscTags", [])
    if not isinstance(tags, list):
        return []
    return [str(tag) for tag in tags]
