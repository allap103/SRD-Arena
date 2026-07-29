from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .creature import CreatureSchema


class PositionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int
    y: int


class GridSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int
    height: int


class BehaviorSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    anchor: PositionSchema | None = None
    radius: int | None = None
    path: list[PositionSchema] = Field(default_factory=list)


class EncounterCreatureSchema(CreatureSchema):
    model_config = ConfigDict(extra="forbid")

    start: PositionSchema
    team_id: str
    controller: Literal["external", "scripted"] | None = None
    behavior: BehaviorSchema | None = None


class EncounterTeamSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    controller: Literal["external", "scripted"]


class EncounterDefinitionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    grid: GridSchema
    creatures: list[EncounterCreatureSchema] = Field(default_factory=list)
    teams: list[EncounterTeamSchema] = Field(default_factory=list, max_length=5)


EncounterDefinitionSchema.model_rebuild()
