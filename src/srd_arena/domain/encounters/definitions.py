"""Provide definitions support for the encounters package."""

from dataclasses import dataclass, field

from ..geometry import Grid, Position


@dataclass
class EncounterBehavior:
    """Represent an encounter behavior."""

    type: str
    anchor: Position | None = None
    radius: int | None = None
    path: list[Position] = field(default_factory=list)


@dataclass
class EncounterParticipant:
    """Represent an encounter participant."""

    creature_id: str
    start: Position
    controller: str | None = None
    behavior: EncounterBehavior | None = None
    takes_turns: bool = True


@dataclass
class EncounterTeam:
    """Represent an encounter team."""

    id: str
    name: str
    members: list[str]
    controller: str


@dataclass
class EncounterTransition:
    """Represent an encounter transition."""

    next_encounter_id: str


@dataclass
class EncounterDefinition:
    """Represent an encounter definition."""

    id: str
    grid: Grid
    participants: list[EncounterParticipant] = field(default_factory=list)
    teams: list[EncounterTeam] = field(default_factory=list)
    victory: EncounterTransition | None = None
    defeat: EncounterTransition | None = None
