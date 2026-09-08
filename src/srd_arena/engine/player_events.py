"""Extract non-privileged facts from structured combat events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent


@dataclass(frozen=True)
class PublicDamage:
    """Describe damage to one creature as reported by a combat event."""

    target_ref: str
    amount: int


def public_damage_from_event(event: CombatEvent) -> tuple[PublicDamage, ...]:
    """Return applied creature damage encoded by one supported event shape."""

    data = event.data
    if event.type == "attack_resolved":
        return _single_damage(data, target_key="target_ref", amount_key="damage")
    if event.type == "attack_hit_retaliation":
        return _single_damage(data, target_key="attacker_ref", amount_key="damage")
    if event.type == "stat_block_action_resolved":
        outcomes = _mapping_sequence(data.get("outcomes"))
        if outcomes:
            return tuple(
                damage
                for outcome in outcomes
                for damage in _single_damage(
                    outcome,
                    target_key="target_ref",
                    amount_key="damage",
                )
            )
        return _single_damage(data, target_key="target_ref", amount_key="damage")
    if event.type in {
        "spell_cast",
        "spell_projectile_resolved",
        "ongoing_effect_resolved",
    }:
        return tuple(
            damage
            for detail in _mapping_sequence(data.get("damage_roll_details"))
            for damage in _single_damage(
                detail,
                target_key="target_ref",
                amount_key="applied_damage",
            )
        )
    return ()


def _single_damage(
    data: Mapping[str, object],
    *,
    target_key: str,
    amount_key: str,
) -> tuple[PublicDamage, ...]:
    target_ref = data.get(target_key)
    amount = data.get(amount_key)
    if not isinstance(target_ref, str) or not isinstance(amount, int) or amount <= 0:
        return ()
    return (PublicDamage(target_ref, amount),)


def _mapping_sequence(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))
