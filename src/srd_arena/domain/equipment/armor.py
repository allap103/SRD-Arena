"""Provide armor support for the equipment package."""

from dataclasses import dataclass


@dataclass
class ArmorStat:
    """Represent an armor stat."""

    slot: str
    type: str
    armor_class: int
    modifier_cap: int
