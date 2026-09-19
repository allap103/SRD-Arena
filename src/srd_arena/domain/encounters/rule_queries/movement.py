"""Encounter queries for per-step and condition-countering movement costs."""

from __future__ import annotations

from srd_arena.domain.creatures import is_two_sizes_smaller
from srd_arena.domain.creatures.attributes import MovementMode
from srd_arena.domain.effects.condition_rules import effective_conditions
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.runtime import RelationshipKind
from srd_arena.domain.geometry import MovementBudget, MovementCost, Position

from ..encounter_models.actions import CreatureRef
from ..spatial import (
    footprint_enters_difficult_terrain,
    movement_mode_for_destination,
)
from ..terrain import TerrainMovementMode
from .context import MovementRuleQueryContext
from .defenses import condition_suppressions
from .numeric import effective_speed, movement_budget_for_mode


def movement_mode_for_step(
    state: MovementRuleQueryContext,
    creature_ref: CreatureRef,
    destination: Position,
) -> MovementMode:
    """Return the speed category used to enter one projected terrain cell."""

    required = movement_mode_for_destination(state, creature_ref, destination)
    if required is TerrainMovementMode.CLIMB:
        return "climb"
    if required is TerrainMovementMode.SWIM:
        return "swim"
    return "walk"


def remaining_movement_for_mode(
    state: MovementRuleQueryContext,
    creature_ref: CreatureRef,
    mode: MovementMode,
    *,
    recompute: bool = False,
) -> MovementBudget:
    """Return movement left after switching to the selected speed.

    The SRD requires distance already spent during the move to be subtracted
    from the newly selected speed.
    """

    creature_state = state.creatures[creature_ref]
    if (
        not recompute
        and creature_state.movement_remaining is not None
        and creature_state.movement_mode == mode
    ):
        return creature_state.movement_remaining
    budget = movement_budget_for_mode(state, creature_ref, mode).budget
    spent = creature_state.movement_spent_this_turn
    return MovementBudget(max(0, int(budget) - int(spent)))


def movement_step_cost(
    state: MovementRuleQueryContext,
    creature_ref: CreatureRef,
    destination: Position | None = None,
) -> MovementCost:
    """Return the composed grid cost of one step.

    Crawling and dragging each add one square to the ordinary one-square entry
    cost. A sufficiently small grappled target adds no dragging cost. Movement
    eligibility handles Speed 0 separately so clients can still advertise a
    disabled movement choice with a useful reason.
    """

    cost = 1
    if destination is not None and footprint_enters_difficult_terrain(
        state,
        creature_ref,
        destination,
    ):
        cost += 1
    if destination is not None:
        mode = movement_mode_for_step(state, creature_ref, destination)
        movement = state.creatures[creature_ref].creature.attributes.movement
        if mode in {"climb", "swim"} and movement.feet_for(mode) is None:
            cost += 1
    applied_conditions = tuple(
        condition
        for condition in state.conditions
        if condition.target_ref == creature_ref
    )
    conditions = effective_conditions(
        applied_conditions,
        condition_suppressions(state, creature_ref).values,
    )
    if conditions.has(Condition.PRONE):
        cost += 1
    grappler_size = state.creatures[creature_ref].creature.size
    grappled_targets = (
        relationship.target_ref
        for relationship in state.relationships
        if relationship.kind is RelationshipKind.GRAPPLING
        and relationship.source_ref == creature_ref
    )
    for target_ref in grappled_targets:
        if not is_two_sizes_smaller(
            state.creatures[target_ref].creature.size,
            grappler_size,
        ):
            cost += 1
    return MovementCost(cost)


def stand_up_movement_cost(
    state: MovementRuleQueryContext,
    creature_ref: CreatureRef,
) -> MovementCost:
    """Return half the creature's effective Speed as a grid movement cost."""

    speed_in_squares = state.definition.grid.movement_budget(
        effective_speed(state, creature_ref).value
    )
    return MovementCost(int(speed_in_squares) // 2)
