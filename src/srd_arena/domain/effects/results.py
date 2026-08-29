"""Carry resolved rule output from source handlers to state application."""

from dataclasses import dataclass, field

from .rule_effects import RuntimeRuleEffect
from .runtime import OngoingEffectLifecycle


@dataclass(frozen=True)
class EffectResult:
    """A resolved effect produced by an action or capability."""

    kind: str
    target_ref: str
    success: bool = True
    data: dict[str, object] = field(default_factory=dict)
    rule_effects: tuple[RuntimeRuleEffect, ...] = ()
    effect_label: str | None = None
    lifecycle: OngoingEffectLifecycle | None = None


@dataclass(frozen=True)
class ActionResolutionResult:
    """Carry source-neutral handler output into encounter state application.

    A spell or class-feature handler identifies the reusable definition it
    resolved, then returns messages, effects, resource changes, and structured
    details without depending on encounter orchestration.

    >>> result = ActionResolutionResult("second_wind", "Second Wind", [], [])
    >>> (result.definition_id, result.definition_name, result.effects)
    ('second_wind', 'Second Wind', [])
    """

    definition_id: str
    definition_name: str
    messages: list[tuple[str, str]]
    effects: list[EffectResult]
    resource_updates: dict[str, int] = field(default_factory=dict)
    details: dict[str, object] = field(default_factory=dict)
