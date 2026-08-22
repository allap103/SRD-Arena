"""Build validated capability schemas into provider-neutral domain models."""

from .capability import build_capability
from .errors import CapabilityBuildError

__all__ = ["CapabilityBuildError", "build_capability"]
