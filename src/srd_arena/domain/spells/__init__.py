"""Expose the public spells package API."""

from .definitions import (
    Spell,
    SpellDamage,
)
from .invocation_grants import SpellInvocationGrant
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
    "SpellInvocationGrant",
    "SpellMaterialComponent",
    "SpellRange",
    "SpellRangeDistance",
]
