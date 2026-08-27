from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from srd_arena.content.capabilities import (
    NonNegativeInt,
    PositiveInt,
)

from .base import SpellCapabilitySchemaModel
from .resolution import SpellResolutionSchema
from .scaling import CasterLevelScalingSchema, SlotScalingSchema
from .targeting import (
    EventSpellTargetSchema,
    SpellRequirementSchema,
    SpellTargetSchema,
)


class CastingTriggerSchema(SpellCapabilitySchemaModel):
    event: Literal[
        "attack_hit",
        "creature_damaged",
        "spell_cast",
        "targeted_by_attack",
        "falling",
    ]
    timing: Literal["before_resolution", "immediately_after", "after_resolution"]
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)
    target: EventSpellTargetSchema | None = None


class OutcomeTriggerSchema(SpellCapabilitySchemaModel):
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
    requirements: list[SpellRequirementSchema] = Field(default_factory=list)
    delay_trigger: Literal[
        "none", "source_turn_start", "source_turn_end", "target_turn_start"
    ] = "none"
    turn_offset: NonNegativeInt = 0
    target: EventSpellTargetSchema | None = None
    per_target_limit: PositiveInt | None = None
    limit_period: Literal["turn", "round", "spell_instance"] | None = None
    resolution: SpellResolutionSchema


class SpellCapabilitySchema(SpellCapabilitySchemaModel):
    target: SpellTargetSchema
    resolution: SpellResolutionSchema
    casting_requirements: list[SpellRequirementSchema] = Field(default_factory=list)
    casting_trigger: CastingTriggerSchema | None = None
    scaling: list[
        Annotated[
            SlotScalingSchema | CasterLevelScalingSchema,
            Field(discriminator="type"),
        ]
    ] = Field(default_factory=list)
    outcome_triggers: list[OutcomeTriggerSchema] = Field(default_factory=list)
    condition_application: Literal["all", "choose_one"] = "all"
    self_removal_blocked_conditions: list[str] = Field(default_factory=list)
    recast_ends_previous: bool = False
