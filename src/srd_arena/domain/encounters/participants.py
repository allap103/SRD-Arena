from __future__ import annotations

from typing import TYPE_CHECKING

from .models import CreatureRef
from .refs import enemy_index
from ..creatures import Creature

if TYPE_CHECKING:
    from .encounter import EncounterState


def creature_controller(state: EncounterState, creature_ref: CreatureRef) -> str:
    if state.control_mode == "all-user":
        return "user"
    creature_id = creature_id_for_ref(state, creature_ref)
    assigned = state.controllers_by_creature.get(creature_id)
    if assigned is not None:
        return assigned
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
    return "user" if creature_ref == "player" else "ai"


def creature_id_for_ref(state: EncounterState, creature_ref: CreatureRef) -> str:
    return (
        "player"
        if creature_ref == "player"
        else state.enemies[enemy_index(creature_ref)].creature_id
    )


def creature_team_id(state: EncounterState, creature_ref: CreatureRef) -> str:
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
    return creature_team_id(state, first_creature_ref) != creature_team_id(
        state, second_creature_ref
    )


def creature_for_ref(
    state: EncounterState, player: Creature, creature_ref: CreatureRef
) -> Creature:
    if creature_ref == "player":
        return player
    return state.enemies[enemy_index(creature_ref)].creature
