"""Stable facade for condition and grapple state operations."""

from .condition_state import (
    ConditionApplicationResult,
    ConditionRejection,
    apply_condition,
    condition_replaces,
    condition_sources_for,
    remove_condition,
    remove_condition_from_source,
)
from .grappling_state import (
    apply_grapple,
    grappled_sources_for,
    grappling_targets_for,
    is_grappled,
    movement_cost_for,
    remove_relationships_for_creature,
)

__all__ = [
    "ConditionApplicationResult",
    "ConditionRejection",
    "apply_condition",
    "apply_grapple",
    "condition_replaces",
    "condition_sources_for",
    "grappled_sources_for",
    "grappling_targets_for",
    "is_grappled",
    "movement_cost_for",
    "remove_condition",
    "remove_condition_from_source",
    "remove_relationships_for_creature",
]
