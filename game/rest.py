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
        recharge = actor.combat_profile.feature_recharge.get(feature_id)
        if recharge == "short_rest" and rest_type in {"short_rest", "long_rest"}:
            previous = actor.feature_uses_remaining.get(feature_id, max_uses)
            actor.feature_uses_remaining[feature_id] = max_uses
            restored += max(0, max_uses - previous)
        elif recharge == "long_rest" and rest_type == "long_rest":
            previous = actor.feature_uses_remaining.get(feature_id, max_uses)
            actor.feature_uses_remaining[feature_id] = max_uses
            restored += max(0, max_uses - previous)
    return restored
