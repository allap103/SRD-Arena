"""Define the attack statistics that an equippable weapon can contribute."""

from dataclasses import dataclass


@dataclass
class WeaponStat:
    """Describe a weapon's damage, reach or range, and rules properties."""

    slot: list[str]
    damage: str
    damage_type: str
    properties: list[str]
    attack_type: str = ""
    range_normal: int | None = None
    range_long: int | None = None
    weapon_category: str = ""
