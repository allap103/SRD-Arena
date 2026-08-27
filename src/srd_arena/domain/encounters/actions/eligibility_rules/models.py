"""Return structured, source-aware reasons why actions cannot be selected."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from ...models import CreatureRef, EncounterAction

if TYPE_CHECKING:
    from ...encounter import EncounterState


@dataclass(frozen=True)
class EligibilityFailure:
    """Explain one rejected rule and retain runtime states responsible for it."""

    code: str
    message: str
    state_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionEligibility:
    """Collect every rule failure discovered for one candidate action."""

    failures: tuple[EligibilityFailure, ...] = ()

    @property
    def allowed(self) -> bool:
        """Return whether no eligibility rule rejected the action.

        >>> ActionEligibility().allowed
        True
        >>> ActionEligibility((EligibilityFailure("stunned", "Actor is stunned"),)).allowed
        False
        """
        return not self.failures


class EligibilityRule(Protocol):
    """Define the eligibility rule contract."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None: ...
