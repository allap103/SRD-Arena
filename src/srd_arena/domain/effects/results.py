from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EffectResult:
    """A resolved effect produced by an action or capability."""

    kind: str
    target_ref: str
    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)
