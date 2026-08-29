"""Describe authored encounter setup independently of its mutable runtime state."""

from dataclasses import dataclass, field

from srd_arena.domain.geometry import Grid, Position


@dataclass
class EncounterBehavior:
    """Configure the simple scripted policy used by an automatic participant."""

    type: str
    anchor: Position | None = None
    radius: int | None = None
    path: list[Position] = field(default_factory=list)


@dataclass
class EncounterParticipant:
    """Place one creature template in an encounter and assign its controller."""

    creature_id: str
    start: Position
    controller: str | None = None
    behavior: EncounterBehavior | None = None
    takes_turns: bool = True


@dataclass
class EncounterTeam:
    """Group participant IDs under shared allegiance and controller ownership."""

    id: str
    name: str
    members: list[str]
    controller: str


@dataclass
class EncounterTransition:
    """Name the encounter entered after a configured outcome."""

    next_encounter_id: str


@dataclass
class EncounterDefinition:
    """Describe an encounter's grid, participants, teams, and outcome links.

    Definitions are loaded content. ``EncounterState`` copies their creature
    templates and creates the mutable initiative, turn, and effect state used
    by one running game.
    """

    id: str
    grid: Grid
    participants: list[EncounterParticipant] = field(default_factory=list)
    teams: list[EncounterTeam] = field(default_factory=list)
    victory: EncounterTransition | None = None
    defeat: EncounterTransition | None = None
