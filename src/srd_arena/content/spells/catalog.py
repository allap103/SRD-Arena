"""Discover and index authored spells by name and source."""

from srd_arena.content.common.catalog import SourceCatalog

from .schema import SpellSchema

SpellCatalog = SourceCatalog[SpellSchema]
