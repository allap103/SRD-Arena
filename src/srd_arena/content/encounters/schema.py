"""Provide schema support for the encounters package."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from srd_arena.content.creatures.schema import CreatureSchema


class PositionSchema(BaseModel):
    """Validate authored position data."""

    model_config = ConfigDict(extra="forbid")

    x: int
    y: int


class GridSchema(BaseModel):
    """Validate authored grid data."""

    model_config = ConfigDict(extra="forbid")

    width: int
    height: int


class BehaviorSchema(BaseModel):
    """Validate authored behavior data."""

    model_config = ConfigDict(extra="forbid")

    type: str
    anchor: PositionSchema | None = None
    radius: int | None = None
    path: list[PositionSchema] = Field(default_factory=list)


class EncounterCreatureSchema(CreatureSchema):
    """Validate authored encounter creature data."""

    model_config = ConfigDict(extra="forbid")

    start: PositionSchema
    team_id: str
    controller: Literal["external", "scripted"] | None = None
    behavior: BehaviorSchema | None = None
    takes_turns: bool = True


class EncounterTeamSchema(BaseModel):
    """Validate authored encounter team data."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    controller: Literal["external", "scripted"]


class EncounterDefinitionSchema(BaseModel):
    """Validate authored encounter definition data."""

    model_config = ConfigDict(extra="forbid")

    id: str
    grid: GridSchema
    creatures: list[EncounterCreatureSchema] = Field(default_factory=list)
    teams: list[EncounterTeamSchema] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def require_unique_creature_ids(self) -> EncounterDefinitionSchema:
        """Require unique creature IDs and at least one turn-taking creature.

        >>> from pydantic import ValidationError
        >>> creature = {"id": "hero", "start": {"x": 0, "y": 0}, "team_id": "heroes"}
        >>> try:
        ...     EncounterDefinitionSchema(id="test", grid={"width": 5, "height": 5},
        ...         creatures=[creature, creature])
        ... except ValidationError as error:
        ...     "IDs must be unique" in str(error)
        True
        """
        creature_ids = [creature.id for creature in self.creatures]
        duplicate_ids = sorted(
            creature_id
            for creature_id in set(creature_ids)
            if creature_ids.count(creature_id) > 1
        )
        if duplicate_ids:
            raise ValueError(
                "Encounter creature IDs must be unique: " + ", ".join(duplicate_ids)
            )
        if self.creatures and not any(
            creature.takes_turns for creature in self.creatures
        ):
            raise ValueError("An encounter requires at least one turn-taking creature.")
        return self


EncounterDefinitionSchema.model_rebuild()
