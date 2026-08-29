"""Keep remaining movement aligned with effective Speed changes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from srd_arena.domain.geometry import MovementBudget

from ..rule_queries.numeric import movement_budget

if TYPE_CHECKING:
    from ..encounter import EncounterState


def reconcile_remaining_movement(
    state: EncounterState,
    creature_refs: Iterable[str],
) -> None:
    """Recompute remaining movement without forgiving distance already spent.

    This is used when an effect changes Speed during a turn. Movement already
    spent remains spent, and a reduced budget cannot produce a negative value.
    """

    for creature_ref in creature_refs:
        creature_state = state.creatures[creature_ref]
        if creature_state.movement_remaining is None:
            continue
        current_budget = movement_budget(
            state,
            creature_ref,
        ).budget
        creature_state.movement_remaining = MovementBudget(
            max(
                0,
                int(current_budget) - int(creature_state.movement_spent_this_turn),
            )
        )
