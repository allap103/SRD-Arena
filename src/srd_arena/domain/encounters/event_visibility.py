"""Snapshot team-shared sight at a specific point in combat resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .participants import creature_team_id
from .rule_queries.visibility import creature_can_see_creature

if TYPE_CHECKING:
    from .encounter import EncounterState


def event_visibility(state: EncounterState) -> tuple[tuple[str, frozenset[str]], ...]:
    """Freeze visible creature references without retaining mutable encounter state."""

    teams: dict[str, set[str]] = {}
    for creature_ref in state.creatures:
        teams.setdefault(creature_team_id(state, creature_ref), set()).add(creature_ref)
    return tuple(
        (
            team_id,
            frozenset(
                subject
                for subject in state.creatures
                if subject in allies
                or any(
                    state.creatures[viewer].is_alive
                    and creature_can_see_creature(state, viewer, subject)
                    for viewer in allies
                )
            ),
        )
        for team_id, allies in teams.items()
    )
