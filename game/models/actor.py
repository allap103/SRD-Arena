from dataclasses import dataclass, field

from ..game_logging import CHANNEL_SYSTEM, get_game_logger
from ..systems.equipment import Equipment
from ..systems.inventory import Inventory
from .attributes import Attributes
from .class_features import ClassRef, CombatProfile, FeatureGrant
from ..rules.types import RuleGrant
from .monster_attack import MonsterAttack

LOGGER = get_game_logger(CHANNEL_SYSTEM)


@dataclass
class Actor:
    id: str
    name: str
    description: str
    inventory: Inventory
    attributes: Attributes
    equipment: Equipment
    current_health: int | None = None
    class_ref: ClassRef | None = None
    feature_grants: list[FeatureGrant] = field(default_factory=list)
    rule_grants: list[RuleGrant] = field(default_factory=list)
    combat_profile: CombatProfile = field(default_factory=CombatProfile)
    feature_uses_remaining: dict[str, int] = field(default_factory=dict)
    monster_attacks: list[MonsterAttack] = field(default_factory=list)

    def __post_init__(self):
        if self.current_health is None:
            self.current_health = self.get_max_health()

    def __str__(self):
        return f"Actor with attributes: {self.attributes} and inventory: {self.inventory.items}"

    def has_item(self, item: str) -> bool:
        return self.inventory.has_item(item)

    def add_item(self, item: str):
        self.inventory.add_item(item)

    def remove_item(self, item: str):
        self.inventory.remove_item(item)

    def show_equipment(self):
        self.equipment.show()

    def equip_item(self, item: str, slot: str):
        if self.inventory.has_item(item):
            self.equipment.equip(item, slot)
            self.inventory.remove_item(item)
        else:
            LOGGER.info(f"Item '{item}' not found in inventory.")

    def unequip_item(self, slot: str):
        removed_item = self.equipment.unequip(slot)
        if removed_item is not None:
            self.inventory.add_item(removed_item)
        else:
            LOGGER.info(f"No item equipped in slot '{slot}'.")

    def get_modifier(self, attribute_value: int) -> int:
        return (attribute_value - 10) // 2

    def get_max_health(self) -> int:
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
