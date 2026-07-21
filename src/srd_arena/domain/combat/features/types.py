from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ...effects.results import EffectResult

DiceRoller = Callable[[int, int], int]


@dataclass(frozen=True)
class CapabilityActionResult:
    capability_id: str
    capability_name: str
    messages: list[tuple[str, str]]
    effects: list[EffectResult]
    resource_updates: dict[str, int] = field(default_factory=dict)
    details: dict[str, object] = field(default_factory=dict)


FeatureActionResult = CapabilityActionResult
