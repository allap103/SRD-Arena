"""Store a creature's core ability scores, defenses, health, and movement modes."""

from dataclasses import dataclass, field


@dataclass
class Movement:
    """Describe the creature's walking speed and optional alternate movement modes."""

    speed_feet: int = 30
    burrow_feet: int | None = None
    climb_feet: int | None = None
    fly_feet: int | None = None
    swim_feet: int | None = None

    @property
    def effective_speed_feet(self) -> int:
        """Return the faster of walking and flying speed.

        >>> Movement(speed_feet=30, fly_feet=60).effective_speed_feet
        60
        >>> Movement(speed_feet=30).effective_speed_feet
        30
        """
        return max(self.speed_feet, self.fly_feet or 0)


@dataclass
class Attributes:
    """Hold the base numerical statistics from which combat values are derived."""

    base_health: int
    level: int
    strength: int
    dexterity: int
    constitution: int
    wisdom: int
    intelligence: int
    charisma: int
    base_armor_class: int
    movement: Movement = field(default_factory=Movement)
    proficiency_bonus: int = 0
    proficiencies: dict[str, object] = field(default_factory=dict)
    saving_throw_proficiencies: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.proficiency_bonus <= 0:
            self.proficiency_bonus = 2 + max(0, self.level - 1) // 4

    def __str__(self) -> str:
        return f"Base Health: {self.base_health}, Level: {self.level}, Strength: {self.strength}, Dexterity: {self.dexterity}, Constitution: {self.constitution}, Wisdom: {self.wisdom}, Intelligence: {self.intelligence}, Charisma: {self.charisma}, Base Armor Class: {self.base_armor_class}"
