"""Expose the public feature rules package API."""

from .registry import resolve_feature_action
from .warlock import dark_ones_blessing_temporary_hit_points

__all__ = [
    "dark_ones_blessing_temporary_hit_points",
    "resolve_feature_action",
]
