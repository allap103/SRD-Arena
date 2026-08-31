"""Validate the authored structure shared by monsters and player characters."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EQUIPMENT_SLOTS = ("right_hand", "left_hand")
EquipmentSlot = Literal[
    "right_hand",
    "left_hand",
]


class CreatureItemReferenceSchema(BaseModel):
    """Define the authored creature-reference fields with name and source."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source: str | None = None


ItemIdOrReference = str | CreatureItemReferenceSchema


class AttributesSchema(BaseModel):
    """Validate a creature's scores, proficiencies, movement, and defenses."""

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
    """Validate each movement speed supplied by an authored creature."""

    model_config = ConfigDict(extra="forbid")

    speed_feet: int = 30


class SpellcastingSchema(BaseModel):
    """Validate creature-specific casting ability, slots, and spell references."""

    model_config = ConfigDict(extra="forbid")

    ability: Literal["str", "dex", "con", "int", "wis", "cha"]
    caster_progression: str
    preparation_mode: str = "fixed"
    cantrips_known: int = 0
    spell_count: int | None = None
    spell_slots: dict[int, int] = Field(default_factory=dict)


class CreatureSchema(BaseModel):
    """Validate a complete creature template before domain construction."""

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
    spellcasting: SpellcastingSchema | None = None
    spells_known: list[StatBlockReferenceSchema] = Field(default_factory=list)
    optional_features: list[StatBlockReferenceSchema] = Field(default_factory=list)
    player_character: str | None = None
    stat_block: StatBlockReferenceSchema | None = None


class StatBlockReferenceSchema(BaseModel):
    """Define the authored creature-reference fields with name and source."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source: str | None = None


CreatureSchema.model_rebuild()
