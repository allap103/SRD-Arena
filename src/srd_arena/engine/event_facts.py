"""Read-only event contract shared by live rules events and captured history."""

from collections.abc import Mapping
from typing import Protocol


class EventFacts(Protocol):
    """Expose only the event fields consumed by player knowledge projectors."""

    @property
    def seq(self) -> int: ...

    @property
    def type(self) -> str: ...

    @property
    def creature_ref(self) -> str | None: ...

    @property
    def data(self) -> Mapping[str, object]: ...

    @property
    def visible_by_team(self) -> tuple[tuple[str, frozenset[str]], ...] | None: ...
