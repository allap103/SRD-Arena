"""Provide types support for the feature rules package."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ...effects.results import EffectResult

DiceRoller = Callable[[int, int], int]


@dataclass(frozen=True)
class CapabilityActionResult:
    """Represent a capability action result."""

    capability_id: str
    capability_name: str
    messages: list[tuple[str, str]]
    effects: list[EffectResult]
    resource_updates: dict[str, int] = field(default_factory=dict)
    details: dict[str, object] = field(default_factory=dict)


FeatureActionResult = CapabilityActionResult
