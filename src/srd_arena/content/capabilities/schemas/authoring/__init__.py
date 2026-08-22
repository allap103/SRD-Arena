"""Rich provider-neutral capability authoring vocabulary."""

from .declarations import (
    ActivationTriggerSchema,
    CapabilityDeclarationSchema,
    OutcomeTriggerSchema,
)
from .resolutions import CapabilityEffectSchema, CapabilityResolutionSchema
from .targets import CapabilityTargetSchema

__all__ = [
    "ActivationTriggerSchema",
    "CapabilityDeclarationSchema",
    "CapabilityEffectSchema",
    "CapabilityResolutionSchema",
    "CapabilityTargetSchema",
    "OutcomeTriggerSchema",
]
