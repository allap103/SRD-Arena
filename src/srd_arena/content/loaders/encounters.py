from pathlib import Path

from ..schemas import EncounterDefinitionSchema
from ...domain.scene import (
    Behavior,
    Encounter,
    EncounterEnemy,
    EncounterResolution,
    EncounterTeam,
    FleeResolution,
    Grid,
    Position,
    Scene,
)
from .source_data import _load_json


def _build_position(position) -> Position:
    return Position(x=position.x, y=position.y)


def _build_encounter(schema: EncounterDefinitionSchema) -> Encounter:
    creature_ids = [creature.creature_id for creature in schema.creatures]
    teams = (
        [
            EncounterTeam(
                id=team.id,
                name=team.name,
                members=list(team.members),
                controller=team.controller,
            )
            for team in schema.teams
        ]
        if schema.teams
        else [
            EncounterTeam(
                id="player",
                name="Player",
                members=["player"],
                controller="user",
            ),
            EncounterTeam(
                id="enemies",
                name="Enemies",
                members=creature_ids,
                controller="ai",
            ),
        ]
    )
    return Encounter(
        grid=Grid(width=schema.grid.width, height=schema.grid.height),
        player_start=_build_position(schema.player_start),
        enemies=[
            EncounterEnemy(
                actor_id=creature.creature_id,
                start=_build_position(creature.start),
                behavior=Behavior(
                    type=creature.behavior.type,
                    anchor=_build_position(creature.behavior.anchor)
                    if creature.behavior.anchor
                    else None,
                    radius=creature.behavior.radius,
                    path=[
                        _build_position(path_position)
                        for path_position in creature.behavior.path
                    ],
                ),
            )
            for creature in schema.creatures
        ],
        teams=teams,
        victory=EncounterResolution(
            next_scene=schema.id,
            message=schema.victory.message,
        ),
        defeat=EncounterResolution(
            next_scene=schema.id,
            message=schema.defeat.message,
        ),
        flee=FleeResolution(
            next_scene=schema.id,
            message=schema.flee.message,
            allowed=schema.flee.allowed,
        )
        if schema.flee
        else None,
    )


def load_encounter(path: str | Path) -> Scene:
    schema = EncounterDefinitionSchema.model_validate(_load_json(path))
    return Scene(
        id=schema.id,
        text=schema.description,
        encounter=_build_encounter(schema),
    )
