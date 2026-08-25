"""Triggered-effect matching for resolved attack rolls."""

from __future__ import annotations

from ....creatures import Creature
from ....effects.triggered import (
    TriggeredEffect,
    matching_effects,
    reroll_eligible_indices,
)
from ...models import AttackOutcome


def matching_damage_reroll_rule(
    attacker: Creature,
    attack: AttackOutcome,
) -> TriggeredEffect | None:
    """Return the first applicable rule that can reroll current damage dice."""
    if attack.damage_roll is None:
        return None
    wielded_with = (
        "two_hands" if "two-handed" in attack.weapon_properties else "one_hand"
    )
    context = {
        "attack_type": attack.attack_type,
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
            if reroll_eligible_indices(effect, attack.damage_roll)
        ),
        None,
    )
