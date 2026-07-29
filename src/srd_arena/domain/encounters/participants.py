from __future__ import annotations

from typing import TYPE_CHECKING

from .models import CreatureRef
from .refs import enemy_index
from ..creatures import Creature

if TYPE_CHECKING:
    from .encounter import EncounterState


def creature_controller(state: EncounterState, actor_ref: CreatureRef) -> str:
    if state.control_mode == "all-user":
        return "user"
    team_id = creature_team_id(state, actor_ref)
    team = next((team for team in state.definition.teams if team.id == team_id), None)
    if team is not None:
        return team.controller
    return "user" if actor_ref == "player" else "ai"


def creature_team_id(state: EncounterState, actor_ref: CreatureRef) -> str:
    actor_id = (
        "player"
        if actor_ref == "player"
        else state.enemies[enemy_index(actor_ref)].actor_id
    )
    team = next(
        (team for team in state.definition.teams if actor_id in team.members), None
    )
    return team.id if team is not None else actor_id


def actors_are_opponents(
    state: EncounterState,
    first_creature_ref: CreatureRef,
    second_creature_ref: CreatureRef,
) -> bool:
    return creature_team_id(state, first_creature_ref) != creature_team_id(
        state, second_creature_ref
    )


def creature_for_ref(
    state: EncounterState, player: Creature, actor_ref: CreatureRef
) -> Creature:
    if actor_ref == "player":
        return player
    return state.enemies[enemy_index(actor_ref)].creature
