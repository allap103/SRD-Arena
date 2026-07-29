from __future__ import annotations

from typing import TYPE_CHECKING

from .models import CreatureRef
from ..creatures import Creature

if TYPE_CHECKING:
    from .encounter import EncounterState


def creature_controller(state: EncounterState, actor_ref: CreatureRef) -> str:
    return state.combatant(actor_ref).controller


def creature_team_id(state: EncounterState, actor_ref: CreatureRef) -> str:
    return state.combatant(actor_ref).team_id


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
    return state.combatant(actor_ref).creature
