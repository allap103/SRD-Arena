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
    """Recompute remaining movement without forgiving distance already spent."""

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
