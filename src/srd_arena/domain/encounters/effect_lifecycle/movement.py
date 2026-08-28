"""Keep remaining movement aligned with effective Speed changes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from ...geometry import MovementBudget

if TYPE_CHECKING:
    from ..encounter import EncounterState


def reconcile_remaining_movement(
    state: EncounterState,
    creature_refs: Iterable[str],
) -> None:
    """Recompute remaining movement without forgiving distance already spent.

    This is used when an effect changes Speed during a turn. Movement already
    spent remains spent, and a reduced budget cannot produce a negative value.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     movement_remaining=30,
    ...     movement_spent_this_turn=20,
    ... )
    >>> rules = SimpleNamespace(
    ...     movement_budget=lambda state, ref: SimpleNamespace(budget=15)
    ... )
    >>> state = SimpleNamespace(creatures={"hero": creature}, combat_rules=rules)
    >>> reconcile_remaining_movement(state, ("hero",))
    >>> int(creature.movement_remaining)
    0
    """

    for creature_ref in creature_refs:
        creature_state = state.creatures[creature_ref]
        if creature_state.movement_remaining is None:
            continue
        current_budget = state.combat_rules.movement_budget(
            state,
            creature_ref,
        ).budget
        creature_state.movement_remaining = MovementBudget(
            max(
                0,
                int(current_budget) - int(creature_state.movement_spent_this_turn),
            )
        )
