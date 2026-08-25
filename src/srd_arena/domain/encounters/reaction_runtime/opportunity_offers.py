"""Discover Opportunity Attack offers and open their decision frames."""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING

from ...geometry import MovementBudget, MovementCost, Position
from ..actions.attack_resolution import can_make_opportunity_attack
from ..behaviors import is_adjacent as _is_adjacent
from ..models import (
    ActionCost,
    DecisionFrame,
    EncounterAction,
    EncounterProgress,
    OpportunityAttackRequest,
    PendingMovement,
    ResumeMovement,
)

if TYPE_CHECKING:
    from ..encounter import EncounterState


def queue_opportunity_attack(
    state: EncounterState,
    *,
    mover_ref: str,
    action_id: str,
    direction: str,
    from_position: Position,
    to_position: Position,
    remaining_movement_after: MovementBudget,
    movement_cost: MovementCost,
    companion_destinations: dict[str, Position],
    progress: EncounterProgress,
    external_only: bool,
    excluded_reactor_refs: Collection[str] = (),
) -> bool:
    """Push the first eligible external Opportunity Attack decision."""

    reactors = [
        (creature_ref, creature_state)
        for creature_ref, creature_state in state.creatures.items()
        if creature_ref != mover_ref
        and creature_ref not in excluded_reactor_refs
        and creature_state.is_alive
        and state._creatures_are_opponents(creature_ref, mover_ref)
        and (
            not external_only
            or state._creature_controller(creature_ref) == "external"
        )
        and state.combat_rules.reaction_eligibility(
            state,
            creature_ref,
            "opportunity_attack",
        ).allowed
        and can_make_opportunity_attack(
            creature_state.creature,
            state.item_templates,
        )
        and _is_adjacent(from_position, creature_state.position)
        and not _is_adjacent(to_position, creature_state.position)
    ]
    if not reactors:
        return False
    reactor_ref, _reactor = reactors[0]

    frame_id = state._next_frame_id()
    trigger_id = state._next_frame_id(prefix="trigger")
    current_frame = state.current_decision()
    movement = PendingMovement(
        action_id=action_id,
        creature_ref=mover_ref,
        direction=direction,
        from_position=Position(from_position.x, from_position.y),
        to_position=Position(to_position.x, to_position.y),
        remaining_movement_after=remaining_movement_after,
        movement_cost=movement_cost,
        trigger_id=trigger_id,
        companion_destinations={
            target_ref: Position(position.x, position.y)
            for target_ref, position in companion_destinations.items()
        },
    )
    state.decision_stack.append(
        DecisionFrame(
            id=frame_id,
            creature_ref=reactor_ref,
            kind="reaction",
            reason="opportunity_attack",
            parent_frame_id=current_frame.id,
            parent_action_id=action_id,
            can_pass=True,
            request=OpportunityAttackRequest(movement),
            continuation=ResumeMovement(movement),
        )
    )
    progress.events.append(
        state._event(
            "trigger_opened",
            creature_ref=reactor_ref,
            frame_id=frame_id,
            action_id=action_id,
            data={
                "kind": "opportunity_attack",
                "target_ref": mover_ref,
                "trigger_id": trigger_id,
            },
        )
    )
    return True


def reaction_actions(state: EncounterState) -> list[EncounterAction]:
    """Build the choices for the active reaction frame."""

    decision = state.current_decision()
    if not isinstance(decision.request, OpportunityAttackRequest):
        creature_ref = decision.creature_ref
        return [
            EncounterAction(
                "Pass reaction",
                "pass",
                id=f"{creature_ref}-reaction-pass",
                creature_ref=creature_ref,
                cost=ActionCost(),
            )
        ]

    movement = decision.request.movement
    target_ref = movement.creature_ref
    target = state.creatures[target_ref]
    reactor_ref = decision.creature_ref
    actions: list[EncounterAction] = []
    if (
        state.combat_rules.reaction_eligibility(
            state,
            reactor_ref,
            "opportunity_attack",
        ).allowed
        and target.is_alive
    ):
        actions.append(
            EncounterAction(
                f"Opportunity attack {target.creature.name}",
                "opportunity_attack",
                target_ref,
                id=(
                    f"{reactor_ref}-opportunity-attack-"
                    f"{target_ref.replace(':', '-')}"
                ),
                creature_ref=reactor_ref,
                source_trigger_id=movement.trigger_id,
                cost=ActionCost(reaction=1),
            )
        )
    actions.append(
        EncounterAction(
            "Pass reaction",
            "pass",
            id=f"{reactor_ref}-reaction-pass",
            creature_ref=reactor_ref,
            source_trigger_id=movement.trigger_id,
        )
    )
    return actions
