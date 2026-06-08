from dataclasses import dataclass


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
    proficiencies: dict = None

    def __init__(self, base_health: int, level: int, strength: int, dexterity: int, constitution: int, wisdom: int, intelligence: int, charisma: int, base_armor_class: int):
        self.base_health = base_health
        self.level = level
        self.strength = strength
        self.dexterity = dexterity
        self.constitution = constitution
        self.wisdom = wisdom
        self.intelligence = intelligence
        self.charisma = charisma
        self.base_armor_class = base_armor_class
        self.proficiencies = {}
        self.proficiency_bonus = round(self.level / 4) + 1

    def __str__(self):
        return f"Base Health: {self.base_health}, Level: {self.level}, Strength: {self.strength}, Dexterity: {self.dexterity}, Constitution: {self.constitution}, Wisdom: {self.wisdom}, Intelligence: {self.intelligence}, Charisma: {self.charisma}, Base Armor Class: {self.base_armor_class}"
