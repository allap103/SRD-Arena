"""Discover and execute explicit choices required by compelled-turn rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.conditions import Condition, build_applied_condition

from ...condition_state import apply_condition
from ...encounter_models.actions import CreatureRef, EncounterAction
from ...encounter_models.decisions import DecisionFrame
from ...encounter_models.resolution import EncounterProgress
from ...rule_queries.compulsions import active_compelled_turn
from ...state_runtime import create_event
from ..capability_support import SUPPORTED_COMPELLED_TURN_INSTRUCTIONS
from .compelled_movement import MOVEMENT_COMPELLED_INSTRUCTIONS

if TYPE_CHECKING:
    from ...encounter import EncounterState


def compelled_turn_action_candidates(
    state: EncounterState,
    creature_ref: CreatureRef,
) -> list[EncounterAction]:
    """Return an explicit turn-ending choice for supported instructions."""

    contribution = active_compelled_turn(state, creature_ref)
    if (
        contribution is None
        or contribution.value.instruction not in SUPPORTED_COMPELLED_TURN_INSTRUCTIONS
    ):
        return []
    instruction = contribution.value.instruction
    label = (
        f"Complete: {instruction.title()}"
        if instruction in MOVEMENT_COMPELLED_INSTRUCTIONS
        else f"Obey: {instruction.title()}"
    )
    return [
        EncounterAction(
            label,
            "obey_compelled_turn",
            instruction,
            id=(
                f"{creature_ref}-obey-{instruction}-"
                f"{contribution.provider_state_id.replace(':', '-')}"
            ),
            creature_ref=creature_ref,
        )
    ]


def execute_compelled_turn_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
    progress: EncounterProgress,
    action_id: str,
) -> bool:
    """Apply a supported compelled instruction and end the creature's turn."""

    if action.kind != "obey_compelled_turn":
        return False
    contribution = active_compelled_turn(state, decision.creature_ref)
    if (
        contribution is None
        or action.value != contribution.value.instruction
        or contribution.value.instruction not in SUPPORTED_COMPELLED_TURN_INSTRUCTIONS
    ):
        raise RuntimeError("A compelled-turn action requires its active instruction.")

    actor = state.creatures[decision.creature_ref]
    instruction = contribution.value.instruction
    condition_applied: bool | None = None
    if instruction == "grovel":
        source = contribution.source
        result = apply_condition(
            state,
            build_applied_condition(
                condition=Condition.PRONE,
                source_ref=source.applied_by_ref or source.definition_id,
                source_label=source.label or source.definition_id,
                target_ref=decision.creature_ref,
                source_kind=source.kind,
                definition_id=source.definition_id,
                origin_id=f"{source.origin_id}:grovel-prone",
            ),
        )
        condition_applied = result.accepted
        message = (
            f"{actor.creature.name} grovels and falls prone."
            if result.accepted
            else (
                f"{actor.creature.name} obeys Grovel but is immune to "
                "the Prone condition."
            )
        )
    elif instruction == "halt":
        message = f"{actor.creature.name} halts and takes no action."
    else:
        message = (
            f"{actor.creature.name} completes the {instruction.title()} instruction."
        )

    progress.messages.append(("system", message))
    progress.events.append(
        create_event(
            state,
            "compelled_turn_resolved",
            creature_ref=decision.creature_ref,
            action_id=action_id,
            data={
                "instruction": instruction,
                "provider_state_id": contribution.provider_state_id,
                "source_definition_id": contribution.source.definition_id,
                "condition_applied": condition_applied,
            },
        )
    )
    return True
