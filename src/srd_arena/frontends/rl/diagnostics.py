"""Spectator-only command boundaries, excluded from policy observations."""

from dataclasses import dataclass

from srd_arena.engine.api import GameCommand, GameplayObservation, PlayerGameUpdate


@dataclass(frozen=True)
class CommandBoundary:
    """One submitted command and its observed post-command state.

    Events may resolve older actions or reactions. Their own action/frame IDs
    carry attribution; proximity to this boundary does not establish causality.
    """

    before: GameplayObservation
    after: GameplayObservation
    controller: str
    command: GameCommand | None
    update: PlayerGameUpdate | None
    rejection: str | None
    seconds: float
