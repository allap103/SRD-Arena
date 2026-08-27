"""Provide attributes support for the creatures package."""

from dataclasses import dataclass, field


@dataclass
class Movement:
    """Represent a movement."""

    speed_feet: int = 30
    burrow_feet: int | None = None
    climb_feet: int | None = None
    fly_feet: int | None = None
    swim_feet: int | None = None

    @property
    def effective_speed_feet(self) -> int:
        return max(self.speed_feet, self.fly_feet or 0)


@dataclass
class Attributes:
    """Represent an attributes."""

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

    def __post_init__(self) -> None:
        if self.proficiency_bonus <= 0:
            self.proficiency_bonus = 2 + max(0, self.level - 1) // 4

    def __str__(self) -> str:
        return f"Base Health: {self.base_health}, Level: {self.level}, Strength: {self.strength}, Dexterity: {self.dexterity}, Constitution: {self.constitution}, Wisdom: {self.wisdom}, Intelligence: {self.intelligence}, Charisma: {self.charisma}, Base Armor Class: {self.base_armor_class}"
