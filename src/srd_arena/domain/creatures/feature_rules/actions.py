"""Provide actions support for the feature rules package."""

from .registry import resolve_feature_action
from .types import (
    CapabilityActionResult,
    DiceRoller,
    FeatureActionResult,
)

__all__ = [
    "CapabilityActionResult",
    "DiceRoller",
    "FeatureActionResult",
    "resolve_feature_action",
]
