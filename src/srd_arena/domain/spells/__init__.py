"""Expose the public spells package API."""

from .definitions import (
    Spell,
    SpellDamage,
)
from .metadata import (
    SpellCastingTime,
    SpellComponents,
    SpellDuration,
    SpellMaterialComponent,
    SpellRange,
    SpellRangeDistance,
)

__all__ = [
    "Spell",
    "SpellCastingTime",
    "SpellComponents",
    "SpellDamage",
    "SpellDuration",
    "SpellMaterialComponent",
    "SpellRange",
    "SpellRangeDistance",
]
