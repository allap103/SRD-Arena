"""Validate the authored structure shared by monsters and player characters."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EQUIPMENT_SLOTS = ("right_hand", "left_hand", "armor")
EquipmentSlot = Literal[
    "right_hand",
    "left_hand",
    "armor",
]
CreatureSize = Literal[
    "T",
    "S",
    "M",
    "L",
    "H",
    "G",
    "tiny",
    "small",
    "medium",
    "large",
    "huge",
    "gargantuan",
]


class CreatureItemReferenceSchema(BaseModel):
    """Define the authored creature-reference fields with name and source."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source: str | None = None


ItemIdOrReference = str | CreatureItemReferenceSchema


class ObservableAppearanceSchema(BaseModel):
    """Validate ordinary visual facts without encoding hidden combat statistics."""

    model_config = ConfigDict(extra="forbid")

    armor_label: str | None = None
    armor_category: Literal[
        "unknown",
        "none",
        "light",
        "medium",
        "heavy",
        "natural",
        "other",
    ] = "unknown"
    has_shield: bool = False
    visible_weapons: tuple[str, ...] = ()
    spellcasting_focus_label: str | None = None
    spellcasting_focus_kind: Literal[
        "none",
        "arcane",
        "divine",
        "druidic",
        "component_pouch",
        "other",
        "unknown",
    ] = "none"
    obvious_features: tuple[str, ...] = ()
    apparent_creature_type: str | None = None


class CharacterSnapshotReferenceSchema(BaseModel):
    """Select one level of a canonical character build."""

    model_config = ConfigDict(extra="forbid")

    build: str
    level: int = Field(ge=1, le=20)


class CharacterOptionReferenceSchema(BaseModel):
    """Identify one selected species, background, feat, or subclass."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    source: str | None = None


class CharacterProfileSchema(BaseModel):
    """Preserve the selected content identities of a compiled fixed build."""

    model_config = ConfigDict(extra="forbid")

    build_id: str
    species: CharacterOptionReferenceSchema
    background: CharacterOptionReferenceSchema
    subclass: CharacterOptionReferenceSchema | None = None
    feats: tuple[CharacterOptionReferenceSchema, ...] = ()
    selected_features: tuple[CharacterOptionReferenceSchema, ...] = ()
    weapon_masteries: tuple[str, ...] = ()


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
    size: CreatureSize | None = None
    current_health: int | None = Field(default=None, ge=0)
    attributes: AttributesSchema = Field(default_factory=AttributesSchema)
    inventory: list[ItemIdOrReference] = Field(default_factory=list)
    equipment: dict[EquipmentSlot, ItemIdOrReference] = Field(default_factory=dict)
    appearance: ObservableAppearanceSchema | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    class_ref: StatBlockReferenceSchema | None = None
    spellcasting: SpellcastingSchema | None = None
    spells_known: list[StatBlockReferenceSchema] = Field(default_factory=list)
    optional_features: list[StatBlockReferenceSchema] = Field(default_factory=list)
    player_character: str | None = None
    character_snapshot: CharacterSnapshotReferenceSchema | None = None
    character_profile: CharacterProfileSchema | None = None
    stat_block: StatBlockReferenceSchema | None = None


class StatBlockReferenceSchema(BaseModel):
    """Define the authored creature-reference fields with name and source."""

    model_config = ConfigDict(extra="forbid")

    name: str
    source: str | None = None


CreatureSchema.model_rebuild()
