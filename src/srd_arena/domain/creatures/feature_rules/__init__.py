"""Expose the public feature rules package API."""

from .registry import resolve_feature_action
from .types import (
    CapabilityActionResult,
    DiceRoller,
)

__all__ = [
    "CapabilityActionResult",
    "DiceRoller",
    "resolve_feature_action",
]
