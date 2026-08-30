"""Internal contracts used while projecting and updating engine sessions."""

from __future__ import annotations

from typing import Protocol

from srd_arena.engine.models import EngineOutcome
from srd_arena.engine.queries import ActionConfiguration, SessionRead


class GameEngine(Protocol):
    """Low-level session operations used by engine command handlers."""

    def read(self) -> SessionRead: ...

    def choose(self, action_id: str) -> EngineOutcome: ...

    def configure_action(
        self,
        action_id: str,
        configuration: ActionConfiguration,
    ) -> EngineOutcome: ...
