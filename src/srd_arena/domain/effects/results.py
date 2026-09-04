"""Carry typed rule output from source handlers to state application."""

from dataclasses import dataclass, field

from srd_arena.domain.geometry import AreaOfEffect

from .rule_effects import RuntimeRuleEffect
from .runtime import EffectDuration, EffectTag, OngoingEffectLifecycle


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
    duration: EffectDuration | None = None
    tags: frozenset[EffectTag] = frozenset()
    area: AreaOfEffect | None = None


@dataclass(frozen=True)
class NoResolutionDetails:
    """Mark an action result that needs no handler-specific metadata."""


@dataclass(frozen=True)
class FeatureResolutionDetails:
    """Describe turn resources granted by a resolved creature feature."""

    granted_actions: int = 0


@dataclass(frozen=True)
class DamageApplication:
    """Identify damage already applied while resolving a spell."""

    target_ref: str
    amount: int


@dataclass(frozen=True)
class AttackHitRetaliationApplication:
    """Capture sourced retaliation before its triggering hit mutates state."""

    protected_target_ref: str
    provider_state_id: str
    source_definition_id: str
    source_ref: str | None
    damage: int
    damage_type: str


@dataclass(frozen=True)
class SpellResolutionDetails:
    """Describe one spell result before it is serialized as a combat event."""

    target_ref: str
    target_label: str
    targets: tuple[tuple[str, str], ...]
    affected_target_refs: tuple[str, ...]
    area: dict[str, object] | None
    spell_level: int
    slot_level: int
    save_details: tuple[dict[str, object], ...] = ()
    attack_roll_details: tuple[dict[str, object], ...] = ()
    damage_roll_details: tuple[dict[str, object], ...] = ()
    healing_roll_details: tuple[dict[str, object], ...] = ()
    temporary_hit_point_details: tuple[dict[str, object], ...] = ()
    damage_applications: tuple[DamageApplication, ...] = ()
    attack_hit_retaliations: tuple[AttackHitRetaliationApplication, ...] = ()
    success: bool = False


type ResolutionDetails = (
    NoResolutionDetails | FeatureResolutionDetails | SpellResolutionDetails
)


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
    details: ResolutionDetails = field(default_factory=NoResolutionDetails)
