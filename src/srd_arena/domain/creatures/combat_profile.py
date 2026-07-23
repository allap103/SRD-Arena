from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .feature_actions import FeatureActionDefinition


@dataclass
class CombatProfile:
    attacks_per_attack_action: int = 1
    bonus_action_options: set[str] = field(default_factory=set)
    reaction_options: set[str] = field(default_factory=set)
    feature_actions: dict[str, FeatureActionDefinition] = field(default_factory=dict)
    feature_uses_max: dict[str, int] = field(default_factory=dict)
    feature_recharge: dict[str, dict[str, int | str]] = field(default_factory=dict)
