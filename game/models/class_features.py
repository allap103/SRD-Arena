from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClassRef:
    name: str
    source: str | None = None


@dataclass(frozen=True)
class FeatureGrant:
    id: str
    name: str
    source_class: str
    level: int
    data: dict[str, object] = field(default_factory=dict)


@dataclass
class CombatProfile:
    attacks_per_attack_action: int = 1
    bonus_action_options: set[str] = field(default_factory=set)
    reaction_options: set[str] = field(default_factory=set)
    feature_uses_max: dict[str, int] = field(default_factory=dict)
    feature_recharge: dict[str, str] = field(default_factory=dict)
