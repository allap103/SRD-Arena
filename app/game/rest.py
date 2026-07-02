from __future__ import annotations

from .models.actor import Actor


def apply_rest(actor: Actor, rest_type: str) -> dict[str, int]:
    restored_resources = _restore_feature_uses(actor, rest_type)
    healed = 0
    if rest_type == "long_rest":
        healed = actor.heal(actor.get_max_health())
    return {
        "healed": healed,
        "restored_resources": restored_resources,
    }


def _restore_feature_uses(actor: Actor, rest_type: str) -> int:
    restored = 0
    for feature_id, max_uses in actor.combat_profile.feature_uses_max.items():
        recharge = actor.combat_profile.feature_recharge.get(feature_id, {})
        previous = actor.feature_uses_remaining.get(feature_id, max_uses)
        updated = previous
        if rest_type == "short_rest":
            short_rest_rule = recharge.get("short_rest")
            if short_rest_rule == "all":
                updated = max_uses
            elif isinstance(short_rest_rule, int):
                updated = min(max_uses, previous + short_rest_rule)
        elif rest_type == "long_rest":
            long_rest_rule = recharge.get("long_rest")
            if long_rest_rule == "all":
                updated = max_uses
            elif isinstance(long_rest_rule, int):
                updated = min(max_uses, previous + long_rest_rule)
        actor.feature_uses_remaining[feature_id] = updated
        restored += max(0, updated - previous)
    return restored
