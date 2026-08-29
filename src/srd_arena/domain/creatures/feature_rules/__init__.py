"""Expose the public feature rules package API."""

from .registry import resolve_feature_action
from .types import CapabilityActionResult

__all__ = [
    "CapabilityActionResult",
    "resolve_feature_action",
]
