"""Keep remaining movement aligned with effective Speed changes."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from ..rule_queries.movement import remaining_movement_for_mode

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
        creature_state.movement_remaining = remaining_movement_for_mode(
            state,
            creature_ref,
            creature_state.movement_mode,
            recompute=True,
        )
