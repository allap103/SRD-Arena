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


class MovementSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speed_feet: int = 30
    feet_per_square: int = 5


class ActorSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str = ""
    attributes: AttributesSchema = Field(default_factory=AttributesSchema)
    inventory: list[str] = Field(default_factory=list)
    equipment: dict[EquipmentSlot, str] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
