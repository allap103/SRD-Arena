from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from ..geometry import Grid, Position


ControllerKind: TypeAlias = Literal["external", "scripted"]


@dataclass
class EncounterBehavior:
    type: str
    anchor: Position | None = None
    radius: int | None = None
    path: list[Position] = field(default_factory=list)


@dataclass
class EncounterParticipant:
    actor_id: str
    start: Position
    behavior: EncounterBehavior | None = None


@dataclass
class EncounterTeam:
    id: str
    name: str
    members: list[str]
    controller: ControllerKind


@dataclass
class EncounterTransition:
    next_encounter_id: str


@dataclass
class EncounterDefinition:
    id: str
    grid: Grid
    participants: list[EncounterParticipant] = field(default_factory=list)
    teams: list[EncounterTeam] = field(default_factory=list)
    victory: EncounterTransition | None = None
    defeat: EncounterTransition | None = None
