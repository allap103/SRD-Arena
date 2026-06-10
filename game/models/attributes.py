from dataclasses import dataclass, field


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
    proficiency_bonus: int = 2
    proficiencies: dict = field(default_factory=dict)

    def __post_init__(self):
        self.proficiency_bonus = round(self.level / 4) + 1

    def __str__(self):
        return f"Base Health: {self.base_health}, Level: {self.level}, Strength: {self.strength}, Dexterity: {self.dexterity}, Constitution: {self.constitution}, Wisdom: {self.wisdom}, Intelligence: {self.intelligence}, Charisma: {self.charisma}, Base Armor Class: {self.base_armor_class}"
