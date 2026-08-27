"""Track attacks made as part of an Attack action."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .encounter import EncounterState
    from .models import CreatureRef, EncounterCreatureState


def spend_attack(
    state: EncounterState,
    creature_ref: CreatureRef,
    *,
    base_attacks: int,
) -> None:
    """Spend one attack and keep the remaining count query-driven."""

    creature_state = state.creatures[creature_ref]
    starts_new_attack_action = creature_state.attack_action_base_attacks <= 0 or (
        creature_state.attacks_remaining <= 0 and creature_state.actions_remaining > 0
    )
    if starts_new_attack_action:
        state._consume_action(allow_magic=False)
        begin_attack_action(
            state,
            creature_ref,
            base_attacks=base_attacks,
        )
    elif creature_state.attacks_remaining <= 0:
        raise RuntimeError("No attack remains in this Attack action.")
    spend_current_attack(state, creature_ref)


def begin_attack_action(
    state: EncounterState,
    creature_ref: CreatureRef,
    *,
    base_attacks: int,
) -> None:
    """Initialize the attack budget for one Attack action."""

    creature_state = state.creatures[creature_ref]
    creature_state.attack_action_base_attacks = base_attacks
    creature_state.attack_action_attacks_used = 0
    reconcile_remaining_attacks(state, (creature_ref,))


def spend_current_attack(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> None:
    """Record one attack within the Attack action already in progress."""

    creature_state = state.creatures[creature_ref]
    if (
        creature_state.attack_action_base_attacks <= 0
        or creature_state.attacks_remaining <= 0
    ):
        raise RuntimeError("No attack remains in this Attack action.")
    creature_state.attack_action_attacks_used += 1
    reconcile_remaining_attacks(state, (creature_ref,))


def clear_attack_action(creature_state: EncounterCreatureState) -> None:
    """Clear both the visible attack count and its progress metadata."""

    creature_state.attacks_remaining = 0
    creature_state.attack_action_base_attacks = 0
    creature_state.attack_action_attacks_used = 0
    creature_state.pending_multiattack.clear()


def reconcile_remaining_attacks(
    state: EncounterState,
    creature_refs: Iterable[CreatureRef],
) -> None:
    """Recompute unused attacks when an Attack-action limit changes."""

    for creature_ref in creature_refs:
        creature_state = state.creatures[creature_ref]
        base = creature_state.attack_action_base_attacks
        if base <= 0:
            continue
        allowed = state.combat_rules.attack_limit(
            state,
            creature_ref,
            base,
        ).value
        remaining = max(
            0,
            allowed - creature_state.attack_action_attacks_used,
        )
        if creature_state.pending_multiattack:
            remaining = min(remaining, len(creature_state.pending_multiattack))
        creature_state.attacks_remaining = remaining
