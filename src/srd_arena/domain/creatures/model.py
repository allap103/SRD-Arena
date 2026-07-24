from dataclasses import dataclass, field

from .equipment import Equipment
from .inventory import Inventory
from .attributes import Attributes
from .classes import ClassRef, SubclassRef
from .class_features import ClassFeature
from .combat_profile import CombatProfile
from ..effects.triggered import TriggeredEffect
from .monster_attack import MonsterAttack
from .spellcasting import Spellcasting
from .statistics import CreatureStatistics

@dataclass
class Creature:
    id: str
    name: str
    description: str
    inventory: Inventory
    attributes: Attributes
    equipment: Equipment
    token_image: str | None = None
    size: str = "M"
    current_health: int | None = None
    class_ref: ClassRef | None = None
    subclass_ref: SubclassRef | None = None
    class_features: list[ClassFeature] = field(default_factory=list)
    triggered_effects: list[TriggeredEffect] = field(default_factory=list)
    combat_profile: CombatProfile = field(default_factory=CombatProfile)
    feature_uses_remaining: dict[str, int] = field(default_factory=dict)
    monster_attacks: list[MonsterAttack] = field(default_factory=list)
    spellcasting: Spellcasting | None = None
    statistics: CreatureStatistics = field(default_factory=CreatureStatistics)
    max_health_override: int | None = None

    def __post_init__(self):
        if self.current_health is None:
            self.current_health = self.get_max_health()

    def __str__(self):
        return f"Creature with attributes: {self.attributes} and inventory: {self.inventory.items}"

    def has_item(self, item: str) -> bool:
        return self.inventory.has_item(item)

    def add_item(self, item: str):
        self.inventory.add_item(item)

    def remove_item(self, item: str):
        self.inventory.remove_item(item)

    def show_equipment(self) -> dict[str, str | None]:
        return self.equipment.show()

    def equip_item(self, item: str, slot: str) -> bool:
        if self.inventory.has_item(item) and self.equipment.equip(item, slot):
            self.inventory.remove_item(item)
            return True
        return False

    def unequip_item(self, slot: str) -> bool:
        removed_item = self.equipment.unequip(slot)
        if removed_item is not None:
            self.inventory.add_item(removed_item)
            return True
        return False

    def get_modifier(self, attribute_value: int) -> int:
        return (attribute_value - 10) // 2

    def get_max_health(self) -> int:
        if self.max_health_override is not None:
            return self.max_health_override
        return (
            self.attributes.base_health
            + self.get_modifier(self.attributes.constitution) * self.attributes.level
        )

    def get_health(self) -> int:
        return self.current_health or 0

    def take_damage(self, amount: int) -> int:
        applied_damage = min(max(amount, 0), self.get_health())
        self.current_health = self.get_health() - applied_damage
        return applied_damage

    def heal(self, amount: int) -> int:
        missing_health = self.get_max_health() - self.get_health()
        applied_healing = min(max(amount, 0), missing_health)
        self.current_health = self.get_health() + applied_healing
        return applied_healing

    def get_armor_class(self) -> int:
        return self.attributes.base_armor_class + self.get_modifier(
            self.attributes.dexterity
        )
