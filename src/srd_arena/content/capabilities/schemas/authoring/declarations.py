"""Top-level authoring models for provider-neutral capabilities."""

from pydantic import Field

from .resolutions import CapabilityResolutionSchema
from srd_arena.content.capabilities.schemas.targets import ExecutableTargetSchema
from srd_arena.content.capabilities.schemas.definitions import (
    CapabilitySchemaBase,
    OutcomeTriggerSchemaBase,
)


class OutcomeTriggerSchema(OutcomeTriggerSchemaBase):
    resolution: CapabilityResolutionSchema


class CapabilityDeclarationSchema(CapabilitySchemaBase):
    target: ExecutableTargetSchema
    resolution: CapabilityResolutionSchema
    outcome_triggers: list[OutcomeTriggerSchema] = Field(default_factory=list)
    blocked_self_removal_conditions: list[str] = Field(default_factory=list)
    reactivation_ends_previous: bool = False
