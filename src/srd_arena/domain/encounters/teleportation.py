"""Apply instantaneous creature relocation without traversing intervening cells."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from srd_arena.domain.geometry import Position

from .encounter_models.actions import CreatureRef
from .forced_movement import end_separated_grapples
from .spatial import placement_is_free

if TYPE_CHECKING:
    from .encounter import EncounterState


@dataclass(frozen=True)
class TeleportResult:
    """Report an applied relocation and grapple relationships it separated."""

    target_ref: CreatureRef
    start: Position
    end: Position
    ended_grapples: tuple[tuple[CreatureRef, CreatureRef], ...] = ()


def apply_teleport(
    state: EncounterState,
    target_ref: CreatureRef,
    destination: Position,
) -> TeleportResult:
    """Relocate a creature to a legal unoccupied footprint."""

    if target_ref not in state.creatures:
        raise ValueError(f"Teleport target '{target_ref}' is not in the encounter.")
    if not placement_is_free(
        state,
        target_ref,
        destination,
        ignored_refs={target_ref},
    ):
        raise ValueError("A teleport destination must be an unoccupied legal space.")
    creature = state.creatures[target_ref]
    start = creature.position
    creature.position = destination
    return TeleportResult(
        target_ref=target_ref,
        start=start,
        end=destination,
        ended_grapples=end_separated_grapples(state, target_ref),
    )
