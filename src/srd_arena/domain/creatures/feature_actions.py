"""Describe executable actions granted by creature and class features."""

from dataclasses import dataclass

from srd_arena.domain.equipment import ArmorCategory


@dataclass(frozen=True)
class FeatureActionDefinition:
    """Bind a feature action's label and economy to its capability grant."""

    feature_id: str
    label: str
    economy: str
    blocked_while_effect_active: bool = False
    requires_active_effect_id: str | None = None
    requires_use: bool = True
    blocked_by_armor_categories: frozenset[ArmorCategory] = frozenset()
