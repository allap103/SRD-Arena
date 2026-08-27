"""Provide weapons support for the equipment package."""

from dataclasses import dataclass


@dataclass
class WeaponStat:
    """Represent a weapon stat."""

    slot: list[str]
    damage: str
    damage_type: str
    properties: list[str]
    attack_type: str = ""
    range_normal: int | None = None
    range_long: int | None = None
    weapon_category: str = ""
