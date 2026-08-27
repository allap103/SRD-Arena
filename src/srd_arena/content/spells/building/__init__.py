"""Concern-based builders for authored spell content."""

from .activation import build_activation
from .capabilities import build_definition, build_spell_definition
from .scaling import build_scaling
from .targeting import (
    creature_types_from_requirements,
    normalize_save_ability,
    target_requirements,
)

__all__ = [
    "build_activation",
    "build_definition",
    "build_scaling",
    "build_spell_definition",
    "creature_types_from_requirements",
    "normalize_save_ability",
    "target_requirements",
]
