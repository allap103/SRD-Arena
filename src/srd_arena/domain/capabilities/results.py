"""Results produced by executable domain capabilities."""

from dataclasses import dataclass, field

from ..effects.results import EffectResult


@dataclass(frozen=True)
class CapabilityActionResult:
    capability_id: str
    capability_name: str
    messages: list[tuple[str, str]]
    effects: list[EffectResult]
    resource_updates: dict[str, int] = field(default_factory=dict)
    details: dict[str, object] = field(default_factory=dict)
