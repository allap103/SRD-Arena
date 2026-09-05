"""Validate universal combat actions exposed by authored grants."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...encounter_models.actions import CreatureRef, EncounterAction
from .models import EligibilityFailure

if TYPE_CHECKING:
    from ...encounter import EncounterState


_DEFERRED_STANDARD_ACTIONS = frozenset({"dash", "dodge", "help", "hide"})


class StandardActionRule:
    """Reject authored standard actions whose shared rule is not implemented."""

    def check(
        self,
        _state: EncounterState,
        _actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None:
        """Return an explicit implementation failure for a deferred action.

        >>> action = EncounterAction("Nimble Escape  Hide", "hide")
        >>> failure = StandardActionRule().check(None, "goblin", action)
        >>> (failure.code, failure.message) if failure else None
        ('unsupported_standard_action', 'Hide is not implemented yet.')
        >>> StandardActionRule().check(
        ...     None, "goblin", EncounterAction("Disengage", "disengage")
        ... ) is None
        True
        """

        if action.kind not in _DEFERRED_STANDARD_ACTIONS:
            return None
        label = action.kind.replace("_", " ").title()
        return EligibilityFailure(
            "unsupported_standard_action",
            f"{label} is not implemented yet.",
        )
