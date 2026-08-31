"""Translate validated equipment records into domain item templates."""

from srd_arena.content.common.sources import slug
from srd_arena.domain.equipment import Item, WeaponStat

from .schema import ItemSchema


def build_item(source_item: ItemSchema) -> Item:
    """Translate one equipment schema into a domain inventory template.

    >>> schema = ItemSchema(
    ...     name="Shortbow", source="X", type="R", dmg1="1d6",
    ...     dmgType="P", range="80/320", property=["2H"])
    >>> item = build_item(schema)
    >>> (item.id, item.weapon_stat.attack_type, item.weapon_stat.range_long)
    ('shortbow', 'ranged', 320)
    """

    if source_item.is_weapon:
        normal_range, long_range = _weapon_range(source_item.range)
        return Item(
            id=slug(source_item.public_name),
            name=source_item.public_name,
            description=_description(source_item),
            category="weapon",
            weapon_stat=WeaponStat(
                slot=["left_hand", "right_hand"],
                damage=source_item.damage or "1d4",
                damage_type=_damage_type(source_item.damage_type),
                properties=[
                    _property_name(prop if isinstance(prop, str) else prop.uid)
                    for prop in source_item.properties
                ],
                attack_type=_attack_type(source_item.type),
                range_normal=normal_range,
                range_long=long_range,
                weapon_category=source_item.weapon_category,
            ),
            item_type=source_item.type,
            misc_tags=source_item.misc_tags,
        )
    return Item(
        id=slug(source_item.public_name),
        name=source_item.public_name,
        description=_description(source_item),
        category="other",
        item_type=source_item.type,
        misc_tags=source_item.misc_tags,
    )


def _description(item: ItemSchema) -> str:
    for entry in (*item.entries, *item.additional_entries):
        if isinstance(entry, str):
            return entry
    return ""


def _attack_type(item_type: str) -> str:
    base_type = item_type.split("|", 1)[0]
    if base_type == "R":
        return "ranged"
    if base_type == "M":
        return "melee"
    return ""


def _weapon_range(value: str | None) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    parts = value.split("/", 1)
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
