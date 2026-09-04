"""Expose the public feature rules package API."""

from .registry import (
    resolve_feature_action,
    spell_invocation_grant,
    spell_invocation_grants,
)
from .warlock import (
    FIENDISH_VIGOR_GRANT_ID,
    dark_ones_blessing_temporary_hit_points,
)

__all__ = [
    "FIENDISH_VIGOR_GRANT_ID",
    "dark_ones_blessing_temporary_hit_points",
    "resolve_feature_action",
    "spell_invocation_grant",
    "spell_invocation_grants",
]
