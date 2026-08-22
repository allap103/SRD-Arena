"""Compatibility aliases for authored spell capabilities."""

from srd_arena.content.capabilities.schemas.authoring.declarations import (
    ActivationTriggerSchema as CastingTriggerSchema,
    CapabilityDeclarationSchema as SpellCapabilitySchema,
    OutcomeTriggerSchema,
)

__all__ = ["CastingTriggerSchema", "OutcomeTriggerSchema", "SpellCapabilitySchema"]
