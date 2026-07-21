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
    behavior: BehaviorSchema | None = None


class EncounterTeamSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    controller: Literal["user", "ai"]


class EncounterOutcomeSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str | None = None


class FleeSchema(EncounterOutcomeSchema):
    allowed: bool = False


class EncounterDefinitionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    grid: GridSchema
    creatures: list[EncounterCreatureSchema] = Field(default_factory=list)
    teams: list[EncounterTeamSchema] = Field(default_factory=list)
    victory: EncounterOutcomeSchema = Field(default_factory=EncounterOutcomeSchema)
    defeat: EncounterOutcomeSchema = Field(default_factory=EncounterOutcomeSchema)
    flee: FleeSchema | None = None


EncounterDefinitionSchema.model_rebuild()
