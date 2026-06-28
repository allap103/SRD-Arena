from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EQUIPMENT_SLOTS = (
    "head",
    "body",
    "legs",
    "feet",
    "hands",
    "right_hand",
    "left_hand",
    "accessory",
)
EquipmentSlot = Literal[
    "head",
    "body",
    "legs",
    "feet",
    "hands",
    "right_hand",
    "left_hand",
    "accessory",
]


class ActorItemReferenceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    source: str | None = None


ItemIdOrReference = str | ActorItemReferenceSchema


class AttributesSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_health: int = 10
    level: int = 1
    movement: "MovementSchema" = Field(default_factory=lambda: MovementSchema())
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    wisdom: int = 10
    intelligence: int = 10
    charisma: int = 10
    base_armor_class: int = 10
    proficiencies: dict[str, object] = Field(default_factory=dict)


class MovementSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speed_feet: int = 30
    feet_per_square: int = 5


class ActorSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None
    description: str = ""
    attributes: AttributesSchema = Field(default_factory=AttributesSchema)
    inventory: list[ItemIdOrReference] = Field(default_factory=list)
    equipment: dict[EquipmentSlot, ItemIdOrReference] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    class_ref: "StatBlockReferenceSchema | None" = None
    optional_features: list["StatBlockReferenceSchema"] = Field(default_factory=list)
    custom_stat_block: str | None = None
    stat_block: "StatBlockReferenceSchema | None" = None


class StatBlockReferenceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    source: str | None = None
