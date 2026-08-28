"""Resolve Python-implemented class feature actions into capability results."""

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
