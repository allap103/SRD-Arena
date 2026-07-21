from dataclasses import dataclass

from .armor import ArmorStat
from .weapons import WeaponStat


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
