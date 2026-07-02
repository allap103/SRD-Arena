from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .actor import EquipmentSlot


class WeaponStatSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: list[EquipmentSlot]
    damage: str
    damage_type: str
    properties: list[str]
    attack_type: str = ""
    range_normal: int | None = None
    range_long: int | None = None
    weapon_category: str = ""


class ArmorStatSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: EquipmentSlot
    type: str
    armor_class: int
    modifier_cap: int


class ItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None
    description: str = ""
    category: Literal["weapon", "armor", "other"] | None = None
    weapon_stat: WeaponStatSchema | None = None
    armor_stat: ArmorStatSchema | None = None
    item_ref: "ItemReferenceSchema | None" = None
    item_type: str = ""
    misc_tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_category_fields(self):
        if self.item_ref is not None:
            return self
        if self.name is None:
            raise ValueError("items require either 'name' or 'item_ref'")
        if self.category is None:
            raise ValueError("items require either 'category' or 'item_ref'")
        if self.category == "weapon" and self.weapon_stat is None:
            raise ValueError("weapon items require a weapon_stat block")
        if self.category == "armor" and self.armor_stat is None:
            raise ValueError("armor items require an armor_stat block")
        if self.category == "other" and (
            self.weapon_stat is not None or self.armor_stat is not None
        ):
            raise ValueError("other items cannot define weapon_stat or armor_stat")
        return self


class ItemReferenceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    source: str | None = None
