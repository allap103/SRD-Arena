"""Provide schema support for the creatures package."""

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


class CreatureItemReferenceSchema(BaseModel):
    """Validate authored creature item reference data."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source: str | None = None


ItemIdOrReference = str | CreatureItemReferenceSchema


class AttributesSchema(BaseModel):
    """Validate authored attributes data."""

    model_config = ConfigDict(extra="forbid")

    base_health: int = 10
    level: int = 1
    movement: MovementSchema = Field(default_factory=lambda: MovementSchema())
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    wisdom: int = 10
    intelligence: int = 10
    charisma: int = 10
    base_armor_class: int = 10
    proficiencies: dict[str, object] = Field(default_factory=dict)


class MovementSchema(BaseModel):
    """Validate authored movement data."""

    model_config = ConfigDict(extra="forbid")

    speed_feet: int = 30


class SpellcastingSchema(BaseModel):
    """Validate authored spellcasting data."""

    model_config = ConfigDict(extra="forbid")

    ability: Literal["str", "dex", "con", "int", "wis", "cha"]
    caster_progression: str
    preparation_mode: str = "fixed"
    cantrips_known: int = 0
    spell_count: int | None = None
    spell_slots: dict[int, int] = Field(default_factory=dict)


class CreatureSchema(BaseModel):
    """Validate authored creature data."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None
    description: str = ""
    token_image: str | None = None
    current_health: int | None = Field(default=None, ge=0)
    attributes: AttributesSchema = Field(default_factory=AttributesSchema)
    inventory: list[ItemIdOrReference] = Field(default_factory=list)
    equipment: dict[EquipmentSlot, ItemIdOrReference] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    class_ref: StatBlockReferenceSchema | None = None
    subclass_ref: SubclassReferenceSchema | None = None
    spellcasting: SpellcastingSchema | None = None
    spells_known: list[StatBlockReferenceSchema] = Field(default_factory=list)
    optional_features: list[StatBlockReferenceSchema] = Field(default_factory=list)
    player_character: str | None = None
    stat_block: StatBlockReferenceSchema | None = None


class StatBlockReferenceSchema(BaseModel):
    """Validate authored stat block reference data."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source: str | None = None


class SubclassReferenceSchema(BaseModel):
    """Validate authored subclass reference data."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source: str | None = None
    class_name: str | None = None
    class_source: str | None = None


CreatureSchema.model_rebuild()
