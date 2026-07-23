from __future__ import annotations

from typing import TYPE_CHECKING

from .models import CreatureRef
from ..creatures import Creature
from ..creatures import is_two_sizes_smaller
from ..effects.conditions import Status

if TYPE_CHECKING:
    from .encounter import EncounterState


def apply_status(state: EncounterState, status: Status) -> None:
    state.conditions = [
        existing for existing in state.conditions if not status_replaces(existing, status)
    ]
    state.conditions.append(status)


def remove_status(state: EncounterState, target_ref: CreatureRef, status_name: str) -> None:
    removed = [
        condition
        for condition in state.conditions
        if condition.target_ref == target_ref and condition.name == status_name
    ]
    state.conditions = [
        condition
        for condition in state.conditions
        if not (condition.target_ref == target_ref and condition.name == status_name)
    ]
    counterparts = {"grappled": "grappling", "grappling": "grappled"}
    for status in removed:
        counterpart = counterparts.get(status.name)
        if counterpart is None:
            continue
        state.conditions = [
            condition
            for condition in state.conditions
            if not (
                condition.name == counterpart
                and condition.target_ref == status.source_ref
                and condition.source_ref == status.target_ref
            )
        ]


def condition_sources_for(
    state: EncounterState, creature_ref: CreatureRef, condition_name: str
) -> tuple[CreatureRef, ...]:
    return tuple(
        condition.source_ref
        for condition in state.conditions
        if condition.target_ref == creature_ref and condition.name == condition_name
    )


def grappled_sources_for(state: EncounterState, creature_ref: CreatureRef) -> tuple[CreatureRef, ...]:
    return condition_sources_for(state, creature_ref, "grappled")


def grappling_targets_for(state: EncounterState, creature_ref: CreatureRef) -> tuple[CreatureRef, ...]:
    return condition_sources_for(state, creature_ref, "grappling")


def is_grappled(state: EncounterState, creature_ref: CreatureRef) -> bool:
    return bool(grappled_sources_for(state, creature_ref))


def movement_cost_for(state: EncounterState, player: Creature, creature_ref: CreatureRef) -> int | None:
    if is_grappled(state, creature_ref):
        return None
    cost = 1
    grappler_size = state._creature_size(player, creature_ref)
    for target_ref in grappling_targets_for(state, creature_ref):
        if not is_two_sizes_smaller(
            state._creature_size(player, target_ref), grappler_size
        ):
            cost += 1
    return cost


def status_replaces(existing: Status, status: Status) -> bool:
    if existing.name != status.name or existing.target_ref != status.target_ref:
        return False
    if existing.name in {"grappled", "grappling"}:
        return existing.source_ref == status.source_ref
    return True
