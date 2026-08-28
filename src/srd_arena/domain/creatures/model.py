"""Aggregate persistent creature statistics, possessions, features, and health."""

import re
from dataclasses import dataclass, field

from ..capabilities import LimitedUsePool
from ..effects.triggered import TriggeredEffect
from .attributes import Attributes
from .class_features import ClassFeature
from .classes import ClassRef, SubclassRef
from .combat_profile import CombatProfile
from .equipment import Equipment
from .inventory import Inventory
from .multiattack import Multiattack
from .spellcasting import Spellcasting
from .stat_block_actions import DeclaredStatBlockAction, StatBlockActionDefinition
from .statistics import CreatureStatistics


@dataclass
class Creature:
    """Own a creature's intrinsic identity, statistics, abilities, and health.

    A creature is independent of any particular encounter. Position, controller,
    team membership, and per-turn resources belong to ``EncounterCreatureState``
    so the same creature template can be instantiated safely in multiple games.
    """

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
    multiattack: Multiattack | None = None
    stat_block_actions: dict[str, StatBlockActionDefinition] = field(
        default_factory=dict
    )
    declared_stat_block_actions: tuple[DeclaredStatBlockAction, ...] = ()
    stat_block_action_resources: dict[str, int] = field(default_factory=dict)
    spellcasting: Spellcasting | None = None
    statistics: CreatureStatistics = field(default_factory=CreatureStatistics)
    max_health_override: int | None = None
    temporary_hit_points: int = 0

    def __post_init__(self) -> None:
        if self.current_health is None:
            self.current_health = self.get_max_health()
        for name, definition in self.stat_block_actions.items():
            resource_pool = getattr(definition, "resource_pool", None)
            if resource_pool is None or name in self.stat_block_action_resources:
                continue
            if isinstance(resource_pool, LimitedUsePool):
                self.stat_block_action_resources[name] = resource_pool.maximum
            else:
                self.stat_block_action_resources[name] = 1

    def __str__(self) -> str:
        return f"Creature with attributes: {self.attributes} and inventory: {self.inventory.items}"

    def has_item(self, item: str) -> bool:
        """Return whether the creature carries an item.

        >>> creature = Creature("hero", "Hero", "", Inventory(["rope"]), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.has_item("rope")
        True
        """
        return self.inventory.has_item(item)

    def add_item(self, item: str) -> None:
        """Add an item to the creature's inventory.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.add_item("rope")
        >>> creature.has_item("rope")
        True
        """
        self.inventory.add_item(item)

    def remove_item(self, item: str) -> None:
        """Remove one matching item from the creature's inventory.

        >>> creature = Creature("hero", "Hero", "", Inventory(["rope"]), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.remove_item("rope")
        >>> creature.has_item("rope")
        False
        """
        self.inventory.remove_item(item)

    def show_equipment(self) -> dict[str, str | None]:
        """Return the creature's current equipment slots.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.show_equipment()["right_hand"] is None
        True
        """
        return self.equipment.show()

    def equip_item(self, item: str, slot: str) -> bool:
        """Move a carried item into a valid equipment slot.

        >>> creature = Creature("hero", "Hero", "", Inventory(["sword"]), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.equip_item("sword", "right_hand")
        True
        >>> (creature.has_item("sword"), creature.show_equipment()["right_hand"])
        (False, 'sword')
        """
        if self.inventory.has_item(item) and self.equipment.equip(item, slot):
            self.inventory.remove_item(item)
            return True
        return False

    def unequip_item(self, slot: str) -> bool:
        """Return an equipped item to the creature's inventory.

        >>> creature = Creature("hero", "Hero", "", Inventory(["sword"]), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.equip_item("sword", "right_hand")
        True
        >>> creature.unequip_item("right_hand")
        True
        >>> creature.has_item("sword")
        True
        """
        removed_item = self.equipment.unequip(slot)
        if removed_item is not None:
            self.inventory.add_item(removed_item)
            return True
        return False

    def get_modifier(self, attribute_value: int) -> int:
        """Calculate the modifier for an ability score.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> (creature.get_modifier(8), creature.get_modifier(15))
        (-1, 2)
        """
        return (attribute_value - 10) // 2

    def get_max_health(self) -> int:
        """Return the creature's intrinsic maximum health.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 2, 14, 12, 14, 10, 10, 10, 10), Equipment())
        >>> creature.get_max_health()
        24
        """
        base = (
            self.max_health_override
            if self.max_health_override is not None
            else self.attributes.base_health
            + self.get_modifier(self.attributes.constitution) * self.attributes.level
        )
        return base

    def get_health(self) -> int:
        """Return current health as a concrete integer.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.get_health()
        20
        """
        return self.current_health or 0

    def take_damage(
        self,
        amount: int,
    ) -> int:
        """Apply already-resolved damage to temporary and current hit points.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.grant_temporary_hit_points(3)
        3
        >>> creature.take_damage(5)
        5
        >>> (creature.temporary_hit_points, creature.get_health())
        (0, 18)
        """
        applied_damage = min(
            max(amount, 0),
            self.get_health() + self.temporary_hit_points,
        )
        absorbed_damage = min(applied_damage, self.temporary_hit_points)
        self.temporary_hit_points -= absorbed_damage
        health_damage = applied_damage - absorbed_damage
        self.current_health = self.get_health() - health_damage
        return applied_damage

    def sense_range(self, sense: str) -> int | None:
        """Return the creature's intrinsic range for a sense.

        >>> stats = CreatureStatistics(senses=("Darkvision 60 ft.",))
        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment(), statistics=stats)
        >>> creature.sense_range("darkvision")
        60
        """
        normalized = sense.casefold()
        ranges: list[int] = []
        for entry in self.statistics.senses:
            match = re.match(
                rf"^{re.escape(normalized)}\s+(\d+)\s*ft\.?$",
                entry.casefold().strip(),
            )
            if match:
                ranges.append(int(match.group(1)))
        return max(ranges) if ranges else None

    def has_sense(self, sense: str) -> bool:
        """Return whether the creature has the requested sense.

        >>> stats = CreatureStatistics(senses=("Darkvision 60 ft.",))
        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment(), statistics=stats)
        >>> creature.has_sense("darkvision")
        True
        """
        return self.sense_range(sense) is not None

    def heal(self, amount: int, *, maximum_health: int | None = None) -> int:
        """Restore health up to the supplied or intrinsic maximum.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.take_damage(8)
        8
        >>> creature.heal(5)
        5
        >>> creature.get_health()
        17
        """
        maximum = self.get_max_health() if maximum_health is None else maximum_health
        missing_health = maximum - self.get_health()
        applied_healing = min(max(amount, 0), missing_health)
        self.current_health = self.get_health() + applied_healing
        return applied_healing

    def grant_temporary_hit_points(self, amount: int) -> int:
        """Replace temporary HP only when the new amount is greater.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.grant_temporary_hit_points(5)
        5
        >>> creature.grant_temporary_hit_points(3)
        0
        >>> creature.temporary_hit_points
        5
        """
        previous = self.temporary_hit_points
        self.temporary_hit_points = max(previous, max(amount, 0))
        return self.temporary_hit_points - previous

    def get_armor_class(self) -> int:
        """Return the creature's intrinsic AC including Dexterity.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 14, 10, 10, 10, 10, 10), Equipment())
        >>> creature.get_armor_class()
        12
        """
        return self.attributes.base_armor_class + self.get_modifier(
            self.attributes.dexterity
        )
