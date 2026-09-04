"""Maintain defeat-triggered lifecycle state for retargetable effects."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..encounter import EncounterState


def mark_retargetable_effects_for_defeat(
    state: EncounterState,
    target_ref: str,
) -> None:
    """Arm active effects whose current target was just defeated."""

    for index, effect in enumerate(state.ongoing_effects):
        retargeting = effect.lifecycle.retarget_on_defeat
        if retargeting is None or target_ref not in effect.target_refs:
            continue
        state.ongoing_effects[index] = replace(
            effect,
            lifecycle=replace(
                effect.lifecycle,
                retarget_on_defeat=replace(
                    retargeting,
                    defeated_target_ref=target_ref,
                    defeated_round=state.round.number,
                    defeated_turn_index=state.turn.index,
                ),
            ),
        )
