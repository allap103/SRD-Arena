"""Provide results support for the effects package."""

from dataclasses import dataclass, field

from .rule_effects import RuntimeRuleEffect


@dataclass(frozen=True)
class EffectResult:
    """A resolved effect produced by an action or capability."""

    kind: str
    target_ref: str
    success: bool = True
    data: dict[str, object] = field(default_factory=dict)
    rule_effects: tuple[RuntimeRuleEffect, ...] = ()
