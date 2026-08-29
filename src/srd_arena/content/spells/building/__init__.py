"""Concern-based builders for authored spell content."""

from .activation import build_activation
from .capabilities import build_definition, build_spell_definition
from .intrinsic_metadata import (
    build_casting_times,
    build_spell_components,
    build_spell_durations,
    build_spell_range,
)
from .scaling import build_scaling
from .targeting import (
    creature_types_from_requirements,
    normalize_save_ability,
    target_requirements,
)

__all__ = [
    "build_activation",
    "build_casting_times",
    "build_definition",
    "build_scaling",
    "build_spell_components",
    "build_spell_definition",
    "build_spell_durations",
    "build_spell_range",
    "creature_types_from_requirements",
    "normalize_save_ability",
    "target_requirements",
]
