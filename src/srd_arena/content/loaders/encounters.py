from dataclasses import dataclass
from pathlib import Path

from srd_arena.content.catalogs import (
    BestiaryCatalog,
    ClassCatalog,
    OptionalFeatureCatalog,
    SpellCatalog,
    SubclassCatalog,
)
from srd_arena.content.schemas import CreatureSchema, EncounterDefinitionSchema
from srd_arena.content.sources import load_json
from srd_arena.domain.creatures import Creature
from srd_arena.domain.encounters import (
    EncounterBehavior,
    EncounterDefinition,
    EncounterParticipant,
    EncounterTeam,
    EncounterTransition,
)
from srd_arena.domain.geometry import Grid, Position
from .creatures import build_creature
from .player_characters import PlayerCharacterTemplates


@dataclass(frozen=True)
class LoadedEncounter:
    definition: EncounterDefinition
    creatures: tuple[Creature, ...]


def _build_position(position) -> Position:
    return Position(x=position.x, y=position.y)


def _build_encounter(schema: EncounterDefinitionSchema) -> EncounterDefinition:
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
    return EncounterDefinition(
        id=schema.id,
        grid=Grid(width=schema.grid.width, height=schema.grid.height),
        participants=[
            EncounterParticipant(
                creature_id=creature.id,
                start=_build_position(creature.start),
                controller=creature.controller,
                behavior=EncounterBehavior(
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
                )
                if creature.behavior
                else None,
                takes_turns=creature.takes_turns,
            )
            for creature in schema.creatures
        ],
        teams=teams,
        victory=EncounterTransition(
            next_encounter_id=schema.id,
        ),
        defeat=EncounterTransition(
            next_encounter_id=schema.id,
        ),
    )


def load_encounter(
    path: str | Path,
    bestiary: BestiaryCatalog | None = None,
    classes: ClassCatalog | None = None,
    player_characters: PlayerCharacterTemplates | None = None,
    optional_features: OptionalFeatureCatalog | None = None,
    subclasses: SubclassCatalog | None = None,
    spells: SpellCatalog | None = None,
) -> LoadedEncounter:
    schema = EncounterDefinitionSchema.model_validate(load_json(path))
    return LoadedEncounter(
        definition=_build_encounter(schema),
        creatures=tuple(
            build_creature(
                CreatureSchema.model_validate(
                    creature.model_dump(
                        exclude_unset=True,
                        exclude={
                            "start",
                            "team_id",
                            "controller",
                            "behavior",
                            "takes_turns",
                        },
                    )
                ),
                bestiary,
                classes,
                player_characters,
                optional_features,
                subclasses,
                spells,
            )
            for creature in schema.creatures
        ),
    )
