"""Validate universal combat actions exposed by authored grants."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...encounter_models.actions import CreatureRef, EncounterAction
from ..creature_actions.hiding import hide_eligibility_failure
from .models import EligibilityFailure

if TYPE_CHECKING:
    from ...encounter import EncounterState


_DEFERRED_STANDARD_ACTIONS = frozenset({"dash", "dodge", "help"})


class StandardActionRule:
    """Reject authored standard actions whose shared rule is not implemented."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Return an explicit implementation failure for a deferred action.

        >>> action = EncounterAction("Help", "help")
        >>> failure = StandardActionRule().check(None, "goblin", action)
        >>> (failure.code, failure.message) if failure else None
        ('unsupported_standard_action', 'Help is not implemented yet.')
        >>> StandardActionRule().check(
        ...     None, "goblin", EncounterAction("Disengage", "disengage")
        ... ) is None
        True
        """

        if action.kind == "hide":
            return hide_eligibility_failure(state, actor_ref)
        if action.kind not in _DEFERRED_STANDARD_ACTIONS:
            return None
        label = action.kind.replace("_", " ").title()
        return EligibilityFailure(
            "unsupported_standard_action",
            f"{label} is not implemented yet.",
        )
