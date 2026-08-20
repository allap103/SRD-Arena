from dataclasses import dataclass, field

from .equipment import Equipment
from .inventory import Inventory
from .attributes import Attributes
from .classes import ClassRef, SubclassRef
from .class_features import ClassFeature
from .combat_profile import CombatProfile
from ..effects.triggered import TriggeredEffect
from ..effects.modifiers import DamageReduction, RollKind, RollModifier
from ..effects.conditions import Condition
from ..rolls.dice import D20RollMode, DieRoller, combine_roll_modes, roll_die
from .multiattack import Multiattack
from .spellcasting import Spellcasting
from .statistics import CreatureStatistics
from .stat_block_actions import DeclaredStatBlockAction, StatBlockActionDefinition


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
    maximum_health_modifiers: dict[str, dict[str, int]] = field(default_factory=dict)
    damage_resistance_sources: dict[str, set[str]] = field(default_factory=dict)
    roll_modifier_sources: dict[str, dict[str, tuple[RollModifier, ...]]] = field(
        default_factory=dict
    )
    armor_class_modifier_sources: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    speed_modifier_sources: dict[str, dict[str, int]] = field(default_factory=dict)
    damage_reduction_sources: dict[str, dict[str, DamageReduction]] = field(
        default_factory=dict
    )
    condition_immunity_sources: dict[str, dict[str, frozenset[Condition]]] = field(
        default_factory=dict
    )

    def __post_init__(self):
        if self.current_health is None:
            self.current_health = self.get_max_health()
        for name, definition in self.stat_block_actions.items():
            resource = getattr(definition, "resource", None)
            if resource is None:
                resource = getattr(definition, "shared_resource", None)
            if resource is None or name in self.stat_block_action_resources:
                continue
            if resource.kind == "uses":
                self.stat_block_action_resources[name] = resource.maximum or 0
            else:
                self.stat_block_action_resources[name] = 1

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
        base = (
            self.max_health_override
            if self.max_health_override is not None
            else self.attributes.base_health
            + self.get_modifier(self.attributes.constitution) * self.attributes.level
        )
        return base + sum(
            max(instances.values(), default=0)
            for instances in self.maximum_health_modifiers.values()
        )

    def set_maximum_health_modifier(
        self,
        definition_id: str,
        origin_id: str,
        value: int,
        *,
        also_modify_current: bool,
    ) -> None:
        previous_maximum = self.get_max_health()
        self.maximum_health_modifiers.setdefault(definition_id, {})[origin_id] = value
        if also_modify_current:
            self.current_health = self.get_health() + (
                self.get_max_health() - previous_maximum
            )

    def remove_maximum_health_modifier(
        self,
        definition_id: str,
        origin_id: str,
        *,
        also_modify_current: bool,
    ) -> None:
        previous_maximum = self.get_max_health()
        instances = self.maximum_health_modifiers.get(definition_id)
        if instances is None:
            return
        instances.pop(origin_id, None)
        if not instances:
            self.maximum_health_modifiers.pop(definition_id, None)
        if also_modify_current:
            self.current_health = max(
                0,
                self.get_health() + self.get_max_health() - previous_maximum,
            )

    def get_health(self) -> int:
        return self.current_health or 0

    def take_damage(
        self,
        amount: int,
        damage_type: str | None = None,
        *,
        roller: DieRoller = roll_die,
    ) -> int:
        if damage_type is not None:
            amount = max(
                0,
                amount - self.resolve_damage_reduction(damage_type, roller),
            )
        if damage_type is not None and self.has_damage_resistance(damage_type):
            amount //= 2
        applied_damage = min(
            max(amount, 0),
            self.get_health() + self.temporary_hit_points,
        )
        absorbed_damage = min(applied_damage, self.temporary_hit_points)
        self.temporary_hit_points -= absorbed_damage
        health_damage = applied_damage - absorbed_damage
        self.current_health = self.get_health() - health_damage
        return applied_damage

    def has_damage_resistance(self, damage_type: str) -> bool:
        return bool(self.damage_resistance_sources.get(damage_type.casefold()))

    def add_damage_resistance(self, damage_type: str, origin_id: str) -> None:
        self.damage_resistance_sources.setdefault(damage_type.casefold(), set()).add(
            origin_id
        )

    def remove_damage_resistance(self, damage_type: str, origin_id: str) -> None:
        sources = self.damage_resistance_sources.get(damage_type.casefold())
        if sources is None:
            return
        sources.discard(origin_id)
        if not sources:
            self.damage_resistance_sources.pop(damage_type.casefold(), None)

    def set_damage_reduction(
        self,
        definition_id: str,
        origin_id: str,
        reduction: DamageReduction,
    ) -> None:
        self.damage_reduction_sources.setdefault(definition_id, {})[origin_id] = (
            reduction
        )

    def remove_damage_reduction(self, definition_id: str, origin_id: str) -> None:
        sources = self.damage_reduction_sources.get(definition_id)
        if sources is None:
            return
        sources.pop(origin_id, None)
        if not sources:
            self.damage_reduction_sources.pop(definition_id, None)

    def resolve_damage_reduction(self, damage_type: str, roller: DieRoller) -> int:
        return sum(
            reduction.resolve(roller)
            for sources in self.damage_reduction_sources.values()
            for reduction in tuple(sources.values())[:1]
            if reduction.damage_type == damage_type.casefold()
        )

    def reset_per_turn_modifiers(self) -> None:
        for sources in self.damage_reduction_sources.values():
            for reduction in sources.values():
                reduction.available = True

    def condition_immunities(self) -> frozenset[Condition]:
        return self.statistics.condition_immunities.union(
            condition
            for sources in self.condition_immunity_sources.values()
            for immunities in sources.values()
            for condition in immunities
        )

    def set_condition_immunities(
        self,
        definition_id: str,
        origin_id: str,
        conditions: frozenset[Condition],
    ) -> None:
        self.condition_immunity_sources.setdefault(definition_id, {})[origin_id] = (
            conditions
        )

    def remove_condition_immunities(self, definition_id: str, origin_id: str) -> None:
        sources = self.condition_immunity_sources.get(definition_id)
        if sources is None:
            return
        sources.pop(origin_id, None)
        if not sources:
            self.condition_immunity_sources.pop(definition_id, None)

    def set_roll_modifiers(
        self,
        definition_id: str,
        origin_id: str,
        modifiers: tuple[RollModifier, ...],
    ) -> None:
        self.roll_modifier_sources.setdefault(definition_id, {})[origin_id] = modifiers

    def remove_roll_modifiers(self, definition_id: str, origin_id: str) -> None:
        sources = self.roll_modifier_sources.get(definition_id)
        if sources is None:
            return
        sources.pop(origin_id, None)
        if not sources:
            self.roll_modifier_sources.pop(definition_id, None)

    def resolve_roll_modifiers(self, roll: RollKind, roller: DieRoller) -> int:
        return sum(
            modifier.resolve(roller)
            for sources in self.roll_modifier_sources.values()
            for modifiers in tuple(sources.values())[:1]
            for modifier in modifiers
            if modifier.roll == roll and modifier.subject == "target"
        )

    def roll_mode(self, roll: RollKind) -> D20RollMode:
        return combine_roll_modes(
            *(
                modifier.roll_mode
                for sources in self.roll_modifier_sources.values()
                for modifiers in tuple(sources.values())[:1]
                for modifier in modifiers
                if modifier.roll == roll
                and modifier.subject == "target"
                and modifier.roll_mode is not None
            )
        )

    def incoming_attack_roll_mode(self) -> D20RollMode:
        return combine_roll_modes(
            *(
                modifier.roll_mode
                for sources in self.roll_modifier_sources.values()
                for modifiers in tuple(sources.values())[:1]
                for modifier in modifiers
                if modifier.roll == "attack_roll"
                and modifier.subject == "attacks_against_target"
                and modifier.roll_mode is not None
            )
        )

    def heal(self, amount: int) -> int:
        missing_health = self.get_max_health() - self.get_health()
        applied_healing = min(max(amount, 0), missing_health)
        self.current_health = self.get_health() + applied_healing
        return applied_healing

    def grant_temporary_hit_points(self, amount: int) -> int:
        """Replace temporary HP only when the new amount is greater."""
        previous = self.temporary_hit_points
        self.temporary_hit_points = max(previous, max(amount, 0))
        return self.temporary_hit_points - previous

    def get_armor_class(self) -> int:
        return (
            self.attributes.base_armor_class
            + self.get_modifier(self.attributes.dexterity)
            + sum(
                max(sources.values(), default=0)
                for sources in self.armor_class_modifier_sources.values()
            )
        )

    def set_armor_class_modifier(
        self, definition_id: str, origin_id: str, value: int
    ) -> None:
        self.armor_class_modifier_sources.setdefault(definition_id, {})[origin_id] = (
            value
        )

    def remove_armor_class_modifier(self, definition_id: str, origin_id: str) -> None:
        sources = self.armor_class_modifier_sources.get(definition_id)
        if sources is None:
            return
        sources.pop(origin_id, None)
        if not sources:
            self.armor_class_modifier_sources.pop(definition_id, None)

    def effective_speed_feet(self) -> int:
        return max(
            0,
            self.attributes.movement.effective_speed_feet
            + sum(
                max(sources.values())
                for sources in self.speed_modifier_sources.values()
                if sources
            ),
        )

    def set_speed_modifier(self, definition_id: str, origin_id: str, feet: int) -> None:
        self.speed_modifier_sources.setdefault(definition_id, {})[origin_id] = feet

    def remove_speed_modifier(self, definition_id: str, origin_id: str) -> None:
        sources = self.speed_modifier_sources.get(definition_id)
        if sources is None:
            return
        sources.pop(origin_id, None)
        if not sources:
            self.speed_modifier_sources.pop(definition_id, None)
