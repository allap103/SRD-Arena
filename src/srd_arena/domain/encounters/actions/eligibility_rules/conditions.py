"""Eligibility rules for actions that counter or apply conditions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.effects.conditions import Condition

from ...encounter_models.actions import CreatureRef, EncounterAction
from ...rule_queries.defenses import condition_immunities
from ...rule_queries.numeric import effective_speed
from .models import EligibilityFailure

if TYPE_CHECKING:
    from ...encounter import EncounterState


class ProneActionRule:
    """Validate voluntary dropping Prone and standing up."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Return why a Prone movement option cannot currently be taken."""

        if action.kind not in {"drop_prone", "stand_up"}:
            return None
        effective = state.effective_conditions_for(actor_ref)
        is_prone = effective.has(Condition.PRONE)
        if action.kind == "stand_up" and not is_prone:
            return EligibilityFailure(
                "condition.prone_required",
                "Only a prone creature can stand up.",
            )
        if action.kind == "drop_prone":
            if is_prone:
                return EligibilityFailure(
                    "condition.already_prone",
                    "The creature is already prone.",
                )
            if Condition.PRONE in condition_immunities(state, actor_ref).values:
                return EligibilityFailure(
                    "condition.prone_immunity",
                    "The creature is immune to the Prone condition.",
                )
        if effective_speed(state, actor_ref).value == 0:
            return EligibilityFailure(
                "condition.prone_speed_zero",
                "A creature whose Speed is 0 cannot take this movement option.",
            )
        return None
