from dataclasses import dataclass, field


@dataclass
class Position:
    x: int
    y: int


@dataclass
class Grid:
    width: int
    height: int


@dataclass
class Behavior:
    type: str
    anchor: Position | None = None
    radius: int | None = None
    path: list[Position] = field(default_factory=list)


@dataclass
class EncounterEnemy:
    actor_id: str
    start: Position
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
    message: str | None = None


@dataclass
class FleeResolution(EncounterResolution):
    allowed: bool = False


@dataclass
class Encounter:
    grid: Grid
    player_start: Position
    enemies: list[EncounterEnemy] = field(default_factory=list)
    teams: list[EncounterTeam] = field(default_factory=list)
    victory: EncounterResolution | None = None
    defeat: EncounterResolution | None = None
    flee: FleeResolution | None = None


@dataclass
class Scene:
    id: str
    text: str
    encounter: Encounter

    def __str__(self):
        return f"Scene ID: {self.id}, Text: {self.text}"

    def __repr__(self):
        return f"Scene(id='{self.id}', text={self.text!r}, encounter={self.encounter!r})"
