from dataclasses import dataclass, field


@dataclass
class Movement:
    speed_feet: int = 30
    feet_per_square: int = 5

    @property
    def squares_per_turn(self) -> int:
        return self.speed_feet // self.feet_per_square


@dataclass
class Attributes:
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
    proficiency_bonus: int = 2
    proficiencies: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.proficiency_bonus = 2 + max(0, self.level - 1) // 4

    def __str__(self) -> str:
        return f"Base Health: {self.base_health}, Level: {self.level}, Strength: {self.strength}, Dexterity: {self.dexterity}, Constitution: {self.constitution}, Wisdom: {self.wisdom}, Intelligence: {self.intelligence}, Charisma: {self.charisma}, Base Armor Class: {self.base_armor_class}"
