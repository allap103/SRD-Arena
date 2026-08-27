"""Provide catalog support for the spells package."""

from srd_arena.content.common.catalog import SourceCatalog

from .schema import SpellSchema

SpellCatalog = SourceCatalog[SpellSchema]
