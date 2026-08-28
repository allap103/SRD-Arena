"""Define the armor statistics that an equippable item can contribute."""

from dataclasses import dataclass


@dataclass
class ArmorStat:
    """Describe an armor item's slot, base AC, and ability-modifier cap."""

    slot: str
    type: str
    armor_class: int
    modifier_cap: int
