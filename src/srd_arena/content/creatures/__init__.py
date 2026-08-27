"""Schemas and loading for authored creature content."""

from .catalog import BestiaryCatalog, load_bestiary_catalog
from .loader import build_creature, load_creature
from .player_characters import (
    PlayerCharacterTemplates,
    load_player_character_templates,
)
from .schema import (
    EQUIPMENT_SLOTS,
    AttributesSchema,
    CreatureItemReferenceSchema,
    CreatureSchema,
    SpellcastingSchema,
    StatBlockReferenceSchema,
)
from .stat_block_schema import (
    BestiaryActionSchema,
    BestiaryFileSchema,
    BestiaryMonsterSchema,
)

__all__ = [
    "EQUIPMENT_SLOTS",
    "AttributesSchema",
    "BestiaryActionSchema",
    "BestiaryCatalog",
    "BestiaryFileSchema",
    "BestiaryMonsterSchema",
    "CreatureItemReferenceSchema",
    "CreatureSchema",
    "PlayerCharacterTemplates",
    "SpellcastingSchema",
    "StatBlockReferenceSchema",
    "build_creature",
    "load_bestiary_catalog",
    "load_creature",
    "load_player_character_templates",
]
