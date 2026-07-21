from dataclasses import dataclass, field

from . import geometry


@dataclass
class Behavior:
    type: str
    anchor: geometry.Position | None = None
    radius: int | None = None
    path: list[geometry.Position] = field(default_factory=list)


@dataclass
class EncounterEnemy:
    actor_id: str
    start: geometry.Position
    behavior: Behavior


@dataclass
class EncounterTeam:
    id: str
    name: str
    members: list[str]
    controller: str


@dataclass
class EncounterResolution:
    next_scene: str


@dataclass
class Encounter:
    grid: geometry.Grid
    player_start: geometry.Position
    enemies: list[EncounterEnemy] = field(default_factory=list)
    teams: list[EncounterTeam] = field(default_factory=list)
    victory: EncounterResolution | None = None
    defeat: EncounterResolution | None = None


@dataclass
class Scene:
    id: str
    encounter: Encounter

    def __str__(self):
        return f"Scene ID: {self.id}"

    def __repr__(self):
        return f"Scene(id='{self.id}', encounter={self.encounter!r})"
