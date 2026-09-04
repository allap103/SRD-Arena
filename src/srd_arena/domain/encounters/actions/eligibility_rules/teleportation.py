"""Validate selected destinations for reusable teleport effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.capabilities import (
    CapabilityDefinition,
    TeleportEffect,
    primary_effects,
)
from srd_arena.domain.geometry import Position, grid_distance_between

from ...encounter_models.actions import CreatureRef
from ...rule_queries.obstructions import creature_has_line_of_effect_to_cell
from ...spatial import creature_position, placement_is_free
from .models import EligibilityFailure

if TYPE_CHECKING:
    from ...encounter import EncounterState


def teleport_destination_failure(
    state: EncounterState,
    actor_ref: CreatureRef,
    definition: CapabilityDefinition,
    aim_point: tuple[float, float] | None,
    *,
    aim_committed: bool,
) -> EligibilityFailure | None:
    """Return why a configured teleport destination is not legal."""

    teleport = next(
        (
            effect
            for effect in primary_effects(definition)
            if isinstance(effect, TeleportEffect)
        ),
        None,
    )
    if teleport is None or not aim_committed:
        return None
    if aim_point is None:
        return EligibilityFailure(
            "teleport_destination_required",
            "Teleportation requires a destination space.",
        )

    destination = Position(int(aim_point[0]), int(aim_point[1]))
    maximum_distance = state.definition.grid.covering_distance_from_feet(
        teleport.distance_feet
    )
    if (
        grid_distance_between(
            creature_position(state, actor_ref),
            destination,
        )
        > maximum_distance
    ):
        return EligibilityFailure(
            "teleport_destination_out_of_range",
            "The teleport destination is out of range.",
        )
    if not placement_is_free(
        state,
        actor_ref,
        destination,
        ignored_refs={actor_ref},
    ):
        return EligibilityFailure(
            "teleport_destination_blocked",
            "The teleport destination must be an unoccupied legal space.",
        )
    if teleport.line_of_sight and not creature_has_line_of_effect_to_cell(
        state,
        actor_ref,
        destination,
    ):
        return EligibilityFailure(
            "teleport_destination_not_visible",
            "The teleport destination is not visible.",
        )
    return None
