from dataclasses import dataclass


@dataclass
class WeaponStat:
    slot: list[str]
    damage: str
    damage_type: str
    properties: list[str]
    attack_type: str = ""
    range_normal: int | None = None
    range_long: int | None = None
    weapon_category: str = ""


@dataclass
class ArmorStat:
    slot: str
    type: str
    armor_class: int
    modifier_cap: int


@dataclass
class Item:
    id: str
    name: str
    description: str
    category: str
    weapon_stat: WeaponStat | None = None
    armor_stat: ArmorStat | None = None
    item_type: str = ""
    misc_tags: list[str] | None = None

    def has_misc_tag(self, tag: str) -> bool:
        return tag in (self.misc_tags or [])
