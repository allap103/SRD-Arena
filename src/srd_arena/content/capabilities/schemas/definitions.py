"""Top-level authored capability declaration schemas."""

from typing import Literal

from pydantic import Field

from .base import CapabilitySchemaModel, NonNegativeInt, PositiveInt
from .requirements import ActionRequirementSchema
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
    attribution: Literal["this_effect", "this_spell", "source"] = "this_spell"
    requirements: list[ActionRequirementSchema] = Field(default_factory=list)
    delay_trigger: Literal[
        "none", "source_turn_start", "source_turn_end", "target_turn_start"
    ] = "none"
    turn_offset: NonNegativeInt = 0
    per_target_limit: PositiveInt | None = None
    limit_period: Literal["turn", "round", "spell_instance"] | None = None


class CapabilitySchemaBase(CapabilitySchemaModel):
    """Fields shared by executable capability declarations."""

    scaling: list[CapabilityScalingSchema] = Field(default_factory=list)
    condition_application: Literal["all", "choose_one"] = "all"
