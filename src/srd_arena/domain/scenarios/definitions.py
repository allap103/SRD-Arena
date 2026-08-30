"""Describe a scenario independently of content files and engine state."""

from dataclasses import dataclass, field

from srd_arena.domain.creatures import Creature
from srd_arena.domain.encounters import EncounterDefinition
from srd_arena.domain.equipment import Item
from srd_arena.domain.geometry import GeometryConfig


@dataclass(frozen=True)
class ScenarioDefinition:
    """Group an ordered series of encounters and their referenced templates.

    A scenario definition is immutable in identity but deliberately contains
    mutable domain templates. Each engine session copies the creature templates
    before play begins.

    >>> from srd_arena.domain.geometry import Grid
    >>> encounter = EncounterDefinition("duel", Grid(5, 5))
    >>> scenario = ScenarioDefinition(
    ...     id="demo", display_name="Demo", encounters={"duel": encounter},
    ...     encounter_order=("duel",), start_encounter_id="duel")
    >>> scenario.get_encounter("duel") is encounter
    True
    """

    id: str
    display_name: str
    encounters: dict[str, EncounterDefinition]
    encounter_order: tuple[str, ...]
    start_encounter_id: str
    creatures: tuple[Creature, ...] = ()
    items: tuple[Item, ...] = ()
    geometry_config: GeometryConfig = field(default_factory=GeometryConfig)

    def __post_init__(self) -> None:
        """Require the ordered encounters and starting point to be available.

        >>> try:
        ...     ScenarioDefinition("empty", "Empty", {}, (), "missing")
        ... except ValueError as error:
        ...     str(error)
        'A scenario must contain at least one encounter.'
        """

        if not self.encounter_order:
            raise ValueError("A scenario must contain at least one encounter.")
        missing = tuple(
            encounter_id
            for encounter_id in self.encounter_order
            if encounter_id not in self.encounters
        )
        if missing:
            raise ValueError(
                "Scenario references missing encounters: " + ", ".join(missing)
            )
        if self.start_encounter_id not in self.encounters:
            raise ValueError(
                f"Scenario starts at missing encounter '{self.start_encounter_id}'."
            )

    def get_encounter(self, encounter_id: str) -> EncounterDefinition:
        """Return an encounter definition by its scenario-local identifier.

        >>> from srd_arena.domain.geometry import Grid
        >>> duel = EncounterDefinition("duel", Grid(2, 2))
        >>> scenario = ScenarioDefinition(
        ...     "demo", "Demo", {"duel": duel}, ("duel",), "duel")
        >>> scenario.get_encounter("duel").grid.width
        2
        """

        return self.encounters[encounter_id]

    def get_creature(self, creature_id: str) -> Creature:
        """Return a referenced creature template by its authored identifier.

        >>> from srd_arena.domain.creatures import Attributes, Equipment, Inventory
        >>> from srd_arena.domain.geometry import Grid
        >>> hero = Creature("hero", "Hero", "", Inventory(),
        ...     Attributes(10, 1, 10, 10, 10, 10, 10, 10, 10), Equipment())
        >>> duel = EncounterDefinition("duel", Grid(1, 1))
        >>> scenario = ScenarioDefinition(
        ...     "demo", "Demo", {"duel": duel}, ("duel",), "duel", (hero,))
        >>> scenario.get_creature("hero").name
        'Hero'
        """

        for creature in self.creatures:
            if creature.id == creature_id:
                return creature
        raise KeyError(f"Creature '{creature_id}' not found.")
