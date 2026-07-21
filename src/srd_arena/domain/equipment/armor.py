from dataclasses import dataclass


@dataclass
class ArmorStat:
    slot: str
    type: str
    armor_class: int
    modifier_cap: int
