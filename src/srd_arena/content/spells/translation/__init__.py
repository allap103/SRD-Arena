"""Concern-based compilation of authored spell content."""

from .activation import compile_activation
from .capabilities import compile_definition
from .scaling import (
    cantrip_damage_by_level,
    slot_damage_increment,
    slot_scaling_value,
    slot_target_increment,
    target_count_by_caster_level,
)

__all__ = [
    "cantrip_damage_by_level",
    "compile_activation",
    "compile_definition",
    "slot_damage_increment",
    "slot_scaling_value",
    "slot_target_increment",
    "target_count_by_caster_level",
]
