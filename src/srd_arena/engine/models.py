"""Provide models support for the engine package."""

from dataclasses import dataclass

from srd_arena.domain.encounters.models import CombatEvent


@dataclass(frozen=True)
class EngineOutcome:
    """Facts emitted by one engine operation.

    The application observes the session separately after the operation. This
    outcome therefore contains only execution facts, not another snapshot of
    the current game state.
    """

    selected_choice_text: str | None = None
    selected_action_id: str | None = None
    messages: tuple[tuple[str, str], ...] = ()
    scene_changed: bool = False
    should_exit: bool = False
    events: tuple[CombatEvent, ...] = ()
