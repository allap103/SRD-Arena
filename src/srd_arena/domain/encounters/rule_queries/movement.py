"""Encounter queries for per-step and condition-countering movement costs."""

from __future__ import annotations

from srd_arena.domain.creatures import is_two_sizes_smaller
from srd_arena.domain.effects.condition_rules import effective_conditions
from srd_arena.domain.effects.conditions import Condition
from srd_arena.domain.effects.runtime import RelationshipKind
from srd_arena.domain.geometry import MovementCost

from ..encounter_models.actions import CreatureRef
from .context import MovementRuleQueryContext
from .defenses import condition_suppressions
from .numeric import effective_speed


def movement_step_cost(
    state: MovementRuleQueryContext,
    creature_ref: CreatureRef,
) -> MovementCost:
    """Return the composed grid cost of one step.

    Crawling and dragging each add one square to the ordinary one-square entry
    cost. A sufficiently small grappled target adds no dragging cost. Movement
    eligibility handles Speed 0 separately so clients can still advertise a
    disabled movement choice with a useful reason.
    """

    cost = 1
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
