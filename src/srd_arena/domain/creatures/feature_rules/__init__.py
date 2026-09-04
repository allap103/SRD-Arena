"""Expose the public feature rules package API."""

from .barbarian import (
    FRENZY_FEATURE_ID,
    RECKLESS_ATTACK_FEATURE_ID,
    frenzy_attack_hit_damage,
    has_reckless_attack,
    reckless_attack_result,
)
from .feats import (
    LUCKY_FEATURE_ID,
    SAVAGE_ATTACKER_EFFECT_ID,
    can_use_alert_initiative_swap,
    creature_has_feat,
    feat_maximum_health_bonus,
    feat_triggered_effects,
    has_lucky,
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
    "FRENZY_FEATURE_ID",
    "LUCKY_FEATURE_ID",
    "RECKLESS_ATTACK_FEATURE_ID",
    "SAVAGE_ATTACKER_EFFECT_ID",
    "can_use_alert_initiative_swap",
    "creature_has_feat",
    "dark_ones_blessing_temporary_hit_points",
    "feat_maximum_health_bonus",
    "feat_triggered_effects",
    "frenzy_attack_hit_damage",
    "has_lucky",
    "has_reckless_attack",
    "initiative_modifier",
    "reckless_attack_result",
    "resolve_feature_action",
    "spell_invocation_grant",
    "spell_invocation_grants",
]
