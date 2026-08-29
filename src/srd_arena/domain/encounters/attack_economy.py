"""Track attacks made as part of an Attack action."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .encounter import EncounterState
    from .encounter_models.actions import CreatureRef
    from .encounter_models.state import EncounterCreatureState


def consume_action(state: EncounterState, *, allow_magic: bool) -> None:
    """Spend the active creature's Action under magic-action restrictions.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(
    ...     active_actions_remaining=1, active_magic_actions_remaining=1
    ... )
    >>> consume_action(state, allow_magic=True)
    >>> (state.active_actions_remaining, state.active_magic_actions_remaining)
    (0, 0)
    """

    if state.active_actions_remaining <= 0:
        raise RuntimeError("No Action remains to consume.")
    non_magic_only_actions = max(
        0,
        state.active_actions_remaining - state.active_magic_actions_remaining,
    )
    if allow_magic:
        if state.active_magic_actions_remaining <= 0:
            raise RuntimeError("No spell-capable Action remains to consume.")
        state.active_magic_actions_remaining -= 1
    elif non_magic_only_actions <= 0 and state.active_magic_actions_remaining > 0:
        state.active_magic_actions_remaining -= 1
    state.active_actions_remaining -= 1


def spend_attack(
    state: EncounterState,
    creature_ref: CreatureRef,
    *,
    base_attacks: int,
) -> None:
    """Spend one attack and keep the remaining count query-driven.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     attack_action_base_attacks=0, attacks_remaining=0,
    ...     actions_remaining=1, attack_action_attacks_used=0,
    ...     pending_multiattack=[],
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={"hero": creature},
    ...     active_actions_remaining=1, active_magic_actions_remaining=1,
    ...     combat_rules=SimpleNamespace(
    ...         attack_limit=lambda state, ref, base: SimpleNamespace(value=base)
    ...     ),
    ... )
    >>> spend_attack(state, "hero", base_attacks=2)
    >>> (creature.attack_action_attacks_used, creature.attacks_remaining)
    (1, 1)
    """

    creature_state = state.creatures[creature_ref]
    starts_new_attack_action = creature_state.attack_action_base_attacks <= 0 or (
        creature_state.attacks_remaining <= 0 and creature_state.actions_remaining > 0
    )
    if starts_new_attack_action:
        consume_action(state, allow_magic=False)
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
    """Initialize the attack budget for one Attack action.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     attack_action_base_attacks=0, attack_action_attacks_used=3,
    ...     attacks_remaining=0, pending_multiattack=[],
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={"hero": creature},
    ...     combat_rules=SimpleNamespace(
    ...         attack_limit=lambda state, ref, base: SimpleNamespace(value=base)
    ...     ),
    ... )
    >>> begin_attack_action(state, "hero", base_attacks=2)
    >>> (creature.attack_action_attacks_used, creature.attacks_remaining)
    (0, 2)
    """

    creature_state = state.creatures[creature_ref]
    creature_state.attack_action_base_attacks = base_attacks
    creature_state.attack_action_attacks_used = 0
    reconcile_remaining_attacks(state, (creature_ref,))


def spend_current_attack(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> None:
    """Record one attack within the Attack action already in progress.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     attack_action_base_attacks=2, attack_action_attacks_used=0,
    ...     attacks_remaining=2, pending_multiattack=[],
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={"hero": creature},
    ...     combat_rules=SimpleNamespace(
    ...         attack_limit=lambda state, ref, base: SimpleNamespace(value=base)
    ...     ),
    ... )
    >>> spend_current_attack(state, "hero")
    >>> (creature.attack_action_attacks_used, creature.attacks_remaining)
    (1, 1)
    """

    creature_state = state.creatures[creature_ref]
    if (
        creature_state.attack_action_base_attacks <= 0
        or creature_state.attacks_remaining <= 0
    ):
        raise RuntimeError("No attack remains in this Attack action.")
    creature_state.attack_action_attacks_used += 1
    reconcile_remaining_attacks(state, (creature_ref,))


def clear_attack_action(creature_state: EncounterCreatureState) -> None:
    """Clear both the visible attack count and its progress metadata.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     attacks_remaining=1, attack_action_base_attacks=2,
    ...     attack_action_attacks_used=1, pending_multiattack=["bite"],
    ... )
    >>> clear_attack_action(creature)
    >>> (creature.attacks_remaining, creature.pending_multiattack)
    (0, [])
    """

    creature_state.attacks_remaining = 0
    creature_state.attack_action_base_attacks = 0
    creature_state.attack_action_attacks_used = 0
    creature_state.pending_multiattack.clear()


def reconcile_remaining_attacks(
    state: EncounterState,
    creature_refs: Iterable[CreatureRef],
) -> None:
    """Recompute unused attacks when an Attack-action limit changes.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     attack_action_base_attacks=3, attack_action_attacks_used=1,
    ...     attacks_remaining=0, pending_multiattack=[],
    ... )
    >>> state = SimpleNamespace(
    ...     creatures={"hero": creature},
    ...     combat_rules=SimpleNamespace(
    ...         attack_limit=lambda state, ref, base: SimpleNamespace(value=2)
    ...     ),
    ... )
    >>> reconcile_remaining_attacks(state, ("hero",))
    >>> creature.attacks_remaining
    1
    """

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
