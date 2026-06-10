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
        from ..content_schema import ItemSchema

        schema = ItemSchema.model_validate(data)
        return cls(
            id=schema.id,
            name=schema.name,
            description=schema.description,
            category=schema.category,
            weapon_stat=WeaponStat(**schema.weapon_stat.model_dump()) if schema.weapon_stat else None,
            armor_stat=ArmorStat(**schema.armor_stat.model_dump()) if schema.armor_stat else None,
        )

    @classmethod
    def from_file(cls, path: str):
        import json

        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)
