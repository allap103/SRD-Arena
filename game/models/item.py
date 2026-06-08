from dataclasses import dataclass


@dataclass
class WeaponStat:
    slot: list
    damage: str
    damage_type: str
    properties: list


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
    weapon_stat: WeaponStat = None
    armor_stat: ArmorStat = None

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            category=data.get("category", ""),
            weapon_stat=WeaponStat(**data.get("weapon_stat", {})) if data.get("weapon_stat") else None,
            armor_stat=ArmorStat(**data.get("armor_stat", {})) if data.get("armor_stat") else None,
        )

    @classmethod
    def from_file(cls, path: str):
        import json

        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)
