from dataclasses import dataclass
from pathlib import Path

from ..schemas import CreatureSchema, EncounterDefinitionSchema
from ...domain.creatures import Creature
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
from .creatures import build_creature
from .types import (
    ClassCatalog,
    CustomStatBlockCatalog,
    OptionalFeatureCatalog,
    SpellCatalog,
    StatBlockCatalog,
    SubclassCatalog,
)


@dataclass(frozen=True)
class LoadedEncounter:
    scene: Scene
    creatures: tuple[Creature, ...]


def _build_position(position) -> Position:
    return Position(x=position.x, y=position.y)


def _build_encounter(schema: EncounterDefinitionSchema) -> Encounter:
    players = [creature for creature in schema.creatures if creature.id == "player"]
    if len(players) != 1:
        raise ValueError(f"Encounter '{schema.id}' must define exactly one player creature.")
    player = players[0]
    team_ids = {team.id for team in schema.teams}
    unknown_team_ids = sorted(
        {creature.team_id for creature in schema.creatures} - team_ids
    )
    if unknown_team_ids:
        raise ValueError(
            f"Encounter '{schema.id}' references unknown teams: {', '.join(unknown_team_ids)}"
        )
    teams = [
        EncounterTeam(
            id=team.id,
            name=team.name,
            members=[
                creature.id
                for creature in schema.creatures
                if creature.team_id == team.id
            ],
            controller=team.controller,
        )
        for team in schema.teams
    ]
    return Encounter(
        grid=Grid(width=schema.grid.width, height=schema.grid.height),
        player_start=_build_position(player.start),
        enemies=[
            EncounterEnemy(
                actor_id=creature.id,
                start=_build_position(creature.start),
                behavior=Behavior(
                    type=creature.behavior.type,
                    anchor=_build_position(creature.behavior.anchor)
                    if creature.behavior and creature.behavior.anchor
                    else None,
                    radius=creature.behavior.radius if creature.behavior else None,
                    path=[
                        _build_position(path_position)
                        for path_position in (
                            creature.behavior.path if creature.behavior else []
                        )
                    ],
                ),
            )
            for creature in schema.creatures
            if creature.id != "player"
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


def load_encounter(
    path: str | Path,
    stat_blocks: StatBlockCatalog | None = None,
    class_blocks: ClassCatalog | None = None,
    custom_stat_blocks: CustomStatBlockCatalog | None = None,
    optional_features: OptionalFeatureCatalog | None = None,
    subclass_blocks: SubclassCatalog | None = None,
    spell_catalog: SpellCatalog | None = None,
) -> LoadedEncounter:
    schema = EncounterDefinitionSchema.model_validate(_load_json(path))
    return LoadedEncounter(
        scene=Scene(
            id=schema.id,
            text=schema.description,
            encounter=_build_encounter(schema),
        ),
        creatures=tuple(
            build_creature(
                CreatureSchema.model_validate(
                    creature.model_dump(
                        exclude_unset=True,
                        exclude={"start", "team_id", "behavior"},
                    )
                ),
                stat_blocks,
                class_blocks,
                custom_stat_blocks,
                optional_features,
                subclass_blocks,
                spell_catalog,
            )
            for creature in schema.creatures
        ),
    )
