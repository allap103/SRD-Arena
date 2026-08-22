"""Authored stat-block action schemas and domain builders."""

from .multiattack import MultiattackCapabilitySchema
from .schema import (
    AttackCapabilitySchema,
    CapabilitySchema,
    NonMultiattackCapabilitySchema,
    SavingThrowActionResolutionSchema,
    SpellcastingCapabilitySchema,
)

__all__ = [
    "AttackCapabilitySchema",
    "CapabilitySchema",
    "MultiattackCapabilitySchema",
    "NonMultiattackCapabilitySchema",
    "SavingThrowActionResolutionSchema",
    "SpellcastingCapabilitySchema",
]
