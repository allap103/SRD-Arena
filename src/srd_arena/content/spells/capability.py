from __future__ import annotations

from typing import Literal

from pydantic import Field

from srd_arena.content.capabilities import (
    CapabilitySchemaBase,
    OutcomeTriggerSchemaBase,
)
from .base import SpellCapabilitySchemaModel
from .targeting import (
    EventSpellTargetSchema,
    SpellRequirementSchema,
    SpellTargetSchema,
)


from .resolution import SpellResolutionSchema


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


class OutcomeTriggerSchema(OutcomeTriggerSchemaBase):
    target: EventSpellTargetSchema | None = None
    resolution: SpellResolutionSchema


class SpellCapabilitySchema(CapabilitySchemaBase):
    target: SpellTargetSchema
    resolution: SpellResolutionSchema
    casting_requirements: list[SpellRequirementSchema] = Field(default_factory=list)
    casting_trigger: CastingTriggerSchema | None = None
    outcome_triggers: list[OutcomeTriggerSchema] = Field(default_factory=list)
    self_removal_blocked_conditions: list[str] = Field(default_factory=list)
    recast_ends_previous: bool = False
