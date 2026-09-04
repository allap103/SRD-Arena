"""Select ordinary movement steps that satisfy a sourced turn instruction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.rule_effects import CompelledTurn
from srd_arena.domain.geometry import Position

from ...behaviors import DIRECTION_DELTAS
from ...encounter_models.actions import CreatureRef, EncounterAction
from ...movement_routing import shortest_approach_directions
from ...rule_queries.models import SourcedRuleContribution
from ...spatial import creature_distance, creature_position
from ..eligibility_rules.common import MovementRule, ResourceRule
from .movement_candidates import movement_action_candidates

if TYPE_CHECKING:
    from ...encounter import EncounterState


MOVEMENT_COMPELLED_INSTRUCTIONS = frozenset({"approach", "flee"})


def legal_compelled_movement_actions(
    state: EncounterState,
    creature_ref: CreatureRef,
    contribution: SourcedRuleContribution[CompelledTurn],
) -> tuple[EncounterAction, ...]:
    """Return legal steps making the greatest progress required by an instruction.

    Distance follows the same square-grid and footprint rules as range. The
    returned actions remain ordinary movement actions, so execution continues
    to use the shared movement, terrain, and reaction pipeline.
    """

    instruction = contribution.value.instruction
    source_ref = contribution.source.applied_by_ref
    if (
        instruction not in MOVEMENT_COMPELLED_INSTRUCTIONS
        or source_ref is None
        or source_ref not in state.creatures
    ):
        return ()

    current_distance = creature_distance(state, creature_ref, source_ref)
    approach_directions = (
        shortest_approach_directions(state, creature_ref, source_ref)
        if instruction == "approach"
        else frozenset()
    )
    if instruction == "approach" and not approach_directions:
        return ()

    movement_rule = MovementRule()
    resource_rule = ResourceRule()
    measured: list[tuple[EncounterAction, int]] = []
    source_position = creature_position(state, creature_ref)
    for action in movement_action_candidates(state, creature_ref):
        if (
            resource_rule.check(state, creature_ref, action) is not None
            or movement_rule.check(state, creature_ref, action) is not None
        ):
            continue
        direction = action.value
        if not isinstance(direction, str):
            continue
        dx, dy = DIRECTION_DELTAS[direction]
        destination = Position(source_position.x + dx, source_position.y + dy)
        distance = int(
            creature_distance(
                state,
                creature_ref,
                source_ref,
                source_position=destination,
            )
        )
        if (instruction == "approach" and direction in approach_directions) or (
            instruction == "flee" and distance > current_distance
        ):
            measured.append((action, distance))

    if not measured:
        return ()
    if instruction == "approach":
        best_distance = min(distance for _, distance in measured)
        return tuple(
            action for action, distance in measured if distance == best_distance
        )
    best_distance = max(distance for _, distance in measured)
    return tuple(action for action, distance in measured if distance == best_distance)
