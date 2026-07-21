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
