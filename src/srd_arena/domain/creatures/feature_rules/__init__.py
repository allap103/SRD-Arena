"""Expose the public feature rules package API."""

from .feats import (
    SAVAGE_ATTACKER_EFFECT_ID,
    can_use_alert_initiative_swap,
    creature_has_feat,
    feat_triggered_effects,
    initiative_modifier,
)
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
    "SAVAGE_ATTACKER_EFFECT_ID",
    "can_use_alert_initiative_swap",
    "creature_has_feat",
    "dark_ones_blessing_temporary_hit_points",
    "feat_triggered_effects",
    "initiative_modifier",
    "resolve_feature_action",
    "spell_invocation_grant",
    "spell_invocation_grants",
]
