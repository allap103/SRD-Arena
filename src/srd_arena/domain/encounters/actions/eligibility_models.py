from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from ..models import CreatureRef, EncounterAction

if TYPE_CHECKING:
    from ..encounter import EncounterState


@dataclass(frozen=True)
class EligibilityFailure:
    code: str
    message: str
    state_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionEligibility:
    failures: tuple[EligibilityFailure, ...] = ()

    @property
    def allowed(self) -> bool:
        return not self.failures


class EligibilityRule(Protocol):
    def check(
        self,
        state: EncounterState,
        actor_ref: CreatureRef,
        action: EncounterAction,
    ) -> EligibilityFailure | None: ...
