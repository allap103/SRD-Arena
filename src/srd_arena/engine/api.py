"""Internal engine contract consumed by application use cases."""

from __future__ import annotations

from typing import Protocol

from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.queries import ActionConfiguration, SessionRead


class GameEngine(Protocol):
    """Typed operations required by the public running-game facade."""

    def read(self) -> SessionRead: ...

    def choose(self, action_id: str) -> EngineOutcome: ...

    def configure_action(
        self,
        action_id: str,
        configuration: ActionConfiguration,
    ) -> EngineOutcome: ...

    def advance_until_input_required(self) -> EngineOutcome: ...

    def advance_one_automatic_action(self) -> EngineOutcome: ...

    def reset(self) -> None: ...
