"""Top-level authoring models for provider-neutral capabilities."""

from typing import Literal

from pydantic import Field

from .resolutions import CapabilityResolutionSchema
from .targets import CapabilityTargetSchema, EventTargetSchema
from srd_arena.content.capabilities.schemas.base import CapabilitySchemaModel
from srd_arena.content.capabilities.schemas.definitions import (
    CapabilitySchemaBase,
    OutcomeTriggerSchemaBase,
)
from srd_arena.content.capabilities.schemas.requirements import (
    CapabilityRequirementSchema,
)


class ActivationTriggerSchema(CapabilitySchemaModel):
    event: Literal[
        "attack_hit",
        "creature_damaged",
        "spell_cast",
        "targeted_by_attack",
        "falling",
    ]
    timing: Literal["before_resolution", "immediately_after", "after_resolution"]
    requirements: list[CapabilityRequirementSchema] = Field(default_factory=list)
    target: EventTargetSchema | None = None


class OutcomeTriggerSchema(OutcomeTriggerSchemaBase):
    target: EventTargetSchema | None = None
    resolution: CapabilityResolutionSchema


class CapabilityDeclarationSchema(CapabilitySchemaBase):
    target: CapabilityTargetSchema
    resolution: CapabilityResolutionSchema
    activation_requirements: list[CapabilityRequirementSchema] = Field(
        default_factory=list
    )
    activation_trigger: ActivationTriggerSchema | None = None
    outcome_triggers: list[OutcomeTriggerSchema] = Field(default_factory=list)
    blocked_self_removal_conditions: list[str] = Field(default_factory=list)
    reactivation_ends_previous: bool = False
