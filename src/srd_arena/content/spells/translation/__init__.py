"""Concern-based compilation of authored spell content."""

from .activation import compile_activation
from .capabilities import compile_definition, compile_spell_definition
from .scaling import compile_scaling
from .targeting import (
    creature_types_from_requirements,
    find_spell,
    normalize_save_ability,
    target_requirements,
)

__all__ = [
    "compile_activation",
    "compile_scaling",
    "compile_definition",
    "compile_spell_definition",
    "creature_types_from_requirements",
    "find_spell",
    "normalize_save_ability",
    "target_requirements",
]
