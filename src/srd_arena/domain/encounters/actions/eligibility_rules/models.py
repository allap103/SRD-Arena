"""Provide models support for the eligibility rules package."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from ...models import CreatureRef, EncounterAction

if TYPE_CHECKING:
    from ...encounter import EncounterState


@dataclass(frozen=True)
class EligibilityFailure:
    """Represent an eligibility failure."""

    code: str
    message: str
    state_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionEligibility:
    """Represent an action eligibility."""

    failures: tuple[EligibilityFailure, ...] = ()

    @property
    def allowed(self) -> bool:
        return not self.failures


class EligibilityRule(Protocol):
    """Define the eligibility rule contract."""

    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None: ...
