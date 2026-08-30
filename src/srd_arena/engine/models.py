"""Define operation results returned by the mutable game engine."""

from dataclasses import dataclass

from srd_arena.domain.encounters.encounter_models.resolution import CombatEvent


@dataclass(frozen=True)
class EngineOutcome:
    """Facts emitted by one engine operation.

    The public engine API observes the session after the operation. This
    outcome therefore contains only execution facts, not another snapshot of
    the current game state.
    """

    selected_choice_text: str | None = None
    selected_action_id: str | None = None
    messages: tuple[tuple[str, str], ...] = ()
    scene_changed: bool = False
    should_exit: bool = False
    events: tuple[CombatEvent, ...] = ()
