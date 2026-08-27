"""Resolve encounter participants, controllers, teams, and creature references."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..creatures import Creature
from .models import CreatureRef

if TYPE_CHECKING:
    from .encounter import EncounterState


def creature_controller(state: EncounterState, creature_ref: CreatureRef) -> str:
    """Return the controller assigned to a creature in this encounter."""

    creature_id = creature_id_for_ref(state, creature_ref)
    participant = next(
        (
            participant
            for participant in state.definition.participants
            if participant.creature_id == creature_id
        ),
        None,
    )
    if participant is not None and participant.controller is not None:
        return participant.controller
    team_id = creature_team_id(state, creature_ref)
    team = next((team for team in state.definition.teams if team.id == team_id), None)
    if team is not None:
        return team.controller
    raise ValueError(f"Creature '{creature_ref}' has no configured controller.")


def creature_id_for_ref(state: EncounterState, creature_ref: CreatureRef) -> str:
    """Resolve a runtime creature reference to its content template identifier."""

    return state.creatures[creature_ref].creature_id


def creature_team_id(state: EncounterState, creature_ref: CreatureRef) -> str:
    """Return the team containing a runtime creature reference."""

    creature_id = creature_id_for_ref(state, creature_ref)
    team = next(
        (team for team in state.definition.teams if creature_id in team.members),
        None,
    )
    return team.id if team is not None else creature_id


def creatures_are_opponents(
    state: EncounterState,
    first_creature_ref: CreatureRef,
    second_creature_ref: CreatureRef,
) -> bool:
    """Return whether two creatures belong to different encounter teams."""

    return creature_team_id(state, first_creature_ref) != creature_team_id(
        state, second_creature_ref
    )


def creature_for_ref(state: EncounterState, creature_ref: CreatureRef) -> Creature:
    """Return the mutable creature owned by a runtime encounter participant."""

    return state.creatures[creature_ref].creature
