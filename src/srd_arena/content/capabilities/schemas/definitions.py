"""Top-level authored capability declaration schemas."""

from typing import Literal

from pydantic import Field

from .base import CapabilitySchemaModel
from .durations import EffectDurationSchema
from .requirements import CapabilityRequirementSchema
from .scaling import CapabilityScalingSchema


class OutcomeTriggerSchemaBase(CapabilitySchemaModel):
    event: Literal[
        "targeted_by_attack",
        "attack_would_hit",
        "attack_hit",
        "targeted_by_spell",
        "spell_cast_nearby",
        "before_target_damaged",
        "target_damaged",
        "target_makes_attack",
        "target_casts_spell",
        "target_deals_damage",
        "adjacent_creature_wakes_target",
        "source_damaged",
        "before_target_reduced_to_zero",
        "target_reduced_to_zero",
        "target_killed",
        "source_turn_start",
        "source_turn_end",
        "target_turn_start",
        "target_turn_end",
        "source_moves",
        "target_moves",
        "effect_ended",
    ]
    requirements: list[CapabilityRequirementSchema] = Field(default_factory=list)


class CapabilitySchemaBase(CapabilitySchemaModel):
    """Fields shared by executable capability declarations."""

    scaling: list[CapabilityScalingSchema] = Field(default_factory=list)
    duration: EffectDurationSchema | None = None
    condition_application: Literal["all", "choose_one"] = "all"
