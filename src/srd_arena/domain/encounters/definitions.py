from dataclasses import dataclass, field

from ..geometry import Grid, Position


@dataclass
class EncounterBehavior:
    type: str
    anchor: Position | None = None
    radius: int | None = None
    path: list[Position] = field(default_factory=list)


@dataclass
class EncounterParticipant:
    creature_id: str
    start: Position
    controller: str | None = None
    behavior: EncounterBehavior | None = None
    takes_turns: bool = True


@dataclass
class EncounterTeam:
    id: str
    name: str
    members: list[str]
    controller: str


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
