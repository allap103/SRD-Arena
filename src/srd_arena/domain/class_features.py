from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ClassRef:
    name: str
    source: str | None = None


@dataclass(frozen=True)
class SubclassRef:
    name: str
    source: str | None = None
    class_name: str | None = None
    class_source: str | None = None


@dataclass(frozen=True)
class FeatureGrant:
    id: str
    name: str
    source_class: str
    level: int
    source_subclass: str | None = None
    data: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class FeatureActionDefinition:
    feature_id: str
    label: str
    economy: str
    target: str
    resolver: str
    combat_only: bool = True


@dataclass
class CombatProfile:
    attacks_per_attack_action: int = 1
    bonus_action_options: set[str] = field(default_factory=set)
    reaction_options: set[str] = field(default_factory=set)
    feature_actions: dict[str, FeatureActionDefinition] = field(default_factory=dict)
    feature_uses_max: dict[str, int] = field(default_factory=dict)
    feature_recharge: dict[str, dict[str, int | str]] = field(default_factory=dict)
