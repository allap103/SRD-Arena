"""Triggered-effect matching for resolved attack rolls."""

from __future__ import annotations

from collections.abc import Collection

from srd_arena.domain.creatures import Creature
from srd_arena.domain.effects.triggered import (
    TriggeredEffect,
    matching_effects,
    reroll_eligible_indices,
)

from ...encounter_models.resolution import AttackOutcome


def matching_damage_reroll_rule(
    attacker: Creature,
    attack: AttackOutcome,
    *,
    excluded_effect_ids: Collection[str] = (),
    allowed_operations: Collection[str] | None = None,
) -> TriggeredEffect | None:
    """Return the first applicable rule that can reroll current damage dice.

    >>> from types import SimpleNamespace
    >>> attacker = SimpleNamespace(triggered_effects=[])
    >>> attack = AttackOutcome([], True, 15, 0, False, {})
    >>> matching_damage_reroll_rule(attacker, attack) is None
    True
    """
    if attack.damage_roll is None:
        return None
    wielded_with = (
        "two_hands" if "two-handed" in attack.weapon_properties else "one_hand"
    )
    context = {
        "attack_type": attack.attack_type,
        "weapon": attack.weapon_id is not None,
        "wielded_with": wielded_with,
        "weapon_properties": list(attack.weapon_properties),
    }
    return next(
        (
            effect
            for effect in matching_effects(
                attacker.triggered_effects,
                "weapon_damage_rolled",
                context,
            )
            if effect.id not in excluded_effect_ids
            and (allowed_operations is None or effect.operation in allowed_operations)
            and (
                effect.operation == "roll_damage_pool_twice"
                or reroll_eligible_indices(effect, attack.damage_roll)
            )
        ),
        None,
    )
