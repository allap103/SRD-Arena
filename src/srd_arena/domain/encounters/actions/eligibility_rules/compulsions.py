"""Restrict ordinary actions while an executable turn instruction is active."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...encounter_models.actions import CreatureRef, EncounterAction
from ...rule_queries.compulsions import active_compelled_turn
from ..creature_actions.compelled import EXECUTABLE_COMPELLED_INSTRUCTIONS
from ..creature_actions.compelled_movement import (
    MOVEMENT_COMPELLED_INSTRUCTIONS,
    legal_compelled_movement_actions,
)
from .models import EligibilityFailure

if TYPE_CHECKING:
    from ...encounter import EncounterState


class CompelledTurnRule:
    """Allow only choices that satisfy a supported active instruction."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Reject actions that conflict with the actor's active instruction."""

        contribution = active_compelled_turn(state, actor_ref)
        if (
            contribution is None
            or contribution.value.instruction not in EXECUTABLE_COMPELLED_INSTRUCTIONS
        ):
            return None

        instruction = contribution.value.instruction
        if instruction in MOVEMENT_COMPELLED_INSTRUCTIONS:
            legal_movements = legal_compelled_movement_actions(
                state,
                actor_ref,
                contribution,
            )
            if action.kind == "move" and action.id in {
                candidate.id for candidate in legal_movements
            }:
                return None
            if (
                action.kind == "obey_compelled_turn"
                and action.value == instruction
                and not legal_movements
            ):
                return None
        elif action.kind == "obey_compelled_turn" and action.value == instruction:
            return None

        return EligibilityFailure(
            "compelled_turn",
            f"The creature must obey the {instruction.title()} instruction.",
            (contribution.provider_state_id,),
        )
