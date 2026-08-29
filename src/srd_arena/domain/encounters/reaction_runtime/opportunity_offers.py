"""Discover Opportunity Attack offers and open their decision frames."""

from __future__ import annotations

from collections.abc import Collection
from typing import TYPE_CHECKING

from srd_arena.domain.geometry import MovementBudget, MovementCost, Position

from ..actions.attack_resolution import can_make_opportunity_attack
from ..behaviors import is_adjacent as _is_adjacent
from ..encounter_models.actions import (
    ActionCost,
    EncounterAction,
)
from ..encounter_models.decisions import (
    DecisionFrame,
    OpportunityAttackRequest,
    PendingMovement,
    ResumeMovement,
)
from ..encounter_models.resolution import EncounterProgress
from ..participants import creature_controller, creatures_are_opponents
from ..rule_queries.permissions import reaction_eligibility
from ..state_runtime import create_event, next_frame_id

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
    """Push the first eligible external Opportunity Attack decision.

    >>> from types import SimpleNamespace
    >>> state = SimpleNamespace(creatures={"hero": SimpleNamespace()})
    >>> queue_opportunity_attack(
    ...     state, mover_ref="hero", action_id="move-1", direction="right",
    ...     from_position=Position(0, 0), to_position=Position(1, 0),
    ...     remaining_movement_after=MovementBudget(5),
    ...     movement_cost=MovementCost(1), companion_destinations={},
    ...     progress=EncounterProgress(), external_only=True,
    ... )
    False
    """

    reactors = [
        (creature_ref, creature_state)
        for creature_ref, creature_state in state.creatures.items()
        if creature_ref != mover_ref
        and creature_ref not in excluded_reactor_refs
        and creature_state.is_alive
        and creatures_are_opponents(state, creature_ref, mover_ref)
        and (
            not external_only or creature_controller(state, creature_ref) == "external"
        )
        and reaction_eligibility(
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

    frame_id = next_frame_id(state)
    trigger_id = next_frame_id(state, prefix="trigger")
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
    state.interrupts.decision_stack.append(
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
        create_event(
            state,
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
    """Build the choices for the active reaction frame.

    Frames without a recognized Opportunity Attack request still expose a
    stable pass choice, allowing future reaction kinds to fail closed.

    >>> from types import SimpleNamespace
    >>> frame = DecisionFrame("reaction", "guard", "reaction", "other")
    >>> actions = reaction_actions(
    ...     SimpleNamespace(current_decision=lambda: frame)
    ... )
    >>> [(action.kind, action.creature_ref) for action in actions]
    [('pass', 'guard')]
    """

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
        reaction_eligibility(
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
                id=(f"{reactor_ref}-opportunity-attack-{target_ref.replace(':', '-')}"),
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
