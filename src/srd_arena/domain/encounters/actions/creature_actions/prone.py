"""Discover and execute the movement options associated with Prone."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.conditions import Condition, build_applied_condition
from srd_arena.domain.geometry import MovementBudget, MovementCost

from ...condition_state import apply_condition, remove_condition
from ...encounter_models.actions import ActionCost, CreatureRef, EncounterAction
from ...encounter_models.decisions import DecisionFrame
from ...encounter_models.resolution import EncounterProgress
from ...rule_queries.movement import stand_up_movement_cost
from ...state_runtime import create_event

if TYPE_CHECKING:
    from ...encounter import EncounterState


def prone_action_candidates(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> list[EncounterAction]:
    """Return the actor's context-appropriate Prone movement option."""

    if state.effective_conditions_for(creature_ref).has(Condition.PRONE):
        return [
            EncounterAction(
                "Stand Up",
                "stand_up",
                id=f"{creature_ref}-stand-up",
                creature_ref=creature_ref,
                cost=ActionCost(movement=stand_up_movement_cost(state, creature_ref)),
            )
        ]
    return [
        EncounterAction(
            "Drop Prone",
            "drop_prone",
            id=f"{creature_ref}-drop-prone",
            creature_ref=creature_ref,
        )
    ]


def execute_prone_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
    progress: EncounterProgress,
    action_id: str,
) -> bool:
    """Execute a recognized Prone movement option without spending an action."""

    if action.kind == "drop_prone":
        actor = state.creatures[decision.creature_ref]
        result = apply_condition(
            state,
            build_applied_condition(
                condition=Condition.PRONE,
                source_ref=decision.creature_ref,
                source_label=actor.creature.name,
                target_ref=decision.creature_ref,
                definition_id="drop_prone",
                origin_id=action_id,
            ),
        )
        if not result.accepted:
            raise RuntimeError("An eligible Drop Prone action must apply Prone.")
        progress.messages.append(("system", f"{actor.creature.name} drops prone."))
        progress.events.append(
            create_event(
                state,
                "condition_applied",
                creature_ref=decision.creature_ref,
                action_id=action_id,
                data={"condition": Condition.PRONE.value},
            )
        )
        return True
    if action.kind != "stand_up":
        return False
    actor = state.creatures[decision.creature_ref]
    movement_cost = stand_up_movement_cost(state, decision.creature_ref)
    actor.movement_remaining = MovementBudget(
        max(0, int(actor.movement_remaining or 0) - int(movement_cost))
    )
    actor.movement_spent_this_turn = MovementCost(
        int(actor.movement_spent_this_turn) + int(movement_cost)
    )
    remove_condition(state, decision.creature_ref, Condition.PRONE)
    progress.messages.append(("system", f"{actor.creature.name} stands up."))
    progress.events.append(
        create_event(
            state,
            "condition_removed",
            creature_ref=decision.creature_ref,
            action_id=action_id,
            data={
                "condition": Condition.PRONE.value,
                "movement_spent": int(movement_cost),
            },
        )
    )
    return True
