"""Define the structured boundary returned by Python feature-rule handlers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ...effects.results import EffectResult

HealingReceiver = Callable[[int], int]


@dataclass(frozen=True)
class CapabilityActionResult:
    """Return messages, effects, resources, and details from a feature action."""

    capability_id: str
    capability_name: str
    messages: list[tuple[str, str]]
    effects: list[EffectResult]
    resource_updates: dict[str, int] = field(default_factory=dict)
    details: dict[str, object] = field(default_factory=dict)
