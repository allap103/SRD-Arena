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
from .lifecycle import (
    automatic_success_condition_immunities,
    automatic_success_traits,
    damage_repeat_save_advantage,
    effect_duration_rounds,
    end_events,
    repeat_failure_conditions,
    repeat_failure_damage,
    repeat_save_trigger,
    save_advantage_against_opponents,
    spell_duration_rounds,
)

__all__ = [
    "cantrip_damage_by_level",
    "automatic_success_condition_immunities",
    "automatic_success_traits",
    "compile_activation",
    "compile_definition",
    "damage_repeat_save_advantage",
    "effect_duration_rounds",
    "end_events",
    "repeat_failure_conditions",
    "repeat_failure_damage",
    "repeat_save_trigger",
    "save_advantage_against_opponents",
    "slot_damage_increment",
    "slot_scaling_value",
    "slot_target_increment",
    "spell_duration_rounds",
    "target_count_by_caster_level",
]
