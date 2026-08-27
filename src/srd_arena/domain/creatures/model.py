"""Aggregate persistent creature statistics, possessions, features, and health."""

import re
from dataclasses import dataclass, field

from ..capabilities import LimitedUsePool
from ..effects.conditions import Condition
from ..effects.modifiers import DamageReduction, RollKind, RollModifier
from ..effects.triggered import TriggeredEffect
from ..rolls.dice import D20RollMode, DieRoller, combine_roll_modes, roll_die
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
    sense_sources: dict[str, dict[str, tuple[tuple[str, int], ...]]] = field(
        default_factory=dict
    )

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
        """Return maximum health including sourced modifiers.

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
        """Set one sourced maximum-health modifier.

        Multiple instances of the same definition do not stack; only the
        strongest instance contributes.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_maximum_health_modifier("aid", "cast-1", 5, also_modify_current=True)
        >>> (creature.get_health(), creature.get_max_health())
        (25, 25)
        """
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
        """Remove one sourced maximum-health modifier.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_maximum_health_modifier("aid", "cast-1", 5, also_modify_current=True)
        >>> creature.remove_maximum_health_modifier("aid", "cast-1", also_modify_current=True)
        >>> (creature.get_health(), creature.get_max_health())
        (20, 20)
        """
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
        """Return current health as a concrete integer.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.get_health()
        20
        """
        return self.current_health or 0

    def take_damage(
        self,
        amount: int,
        damage_type: str | None = None,
        *,
        roller: DieRoller = roll_die,
    ) -> int:
        """Apply damage after reductions, resistance, and temporary HP.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.grant_temporary_hit_points(3)
        3
        >>> creature.take_damage(5)
        5
        >>> (creature.temporary_hit_points, creature.get_health())
        (0, 18)
        """
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
        """Return whether any active source grants damage resistance.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.add_damage_resistance("Fire", "spell:protection")
        >>> creature.has_damage_resistance("fire")
        True
        """
        return bool(self.damage_resistance_sources.get(damage_type.casefold()))

    def add_damage_resistance(self, damage_type: str, origin_id: str) -> None:
        """Add a sourced resistance without replacing other sources.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.add_damage_resistance("fire", "spell:protection")
        >>> creature.take_damage(5, "fire")
        2
        """
        self.damage_resistance_sources.setdefault(damage_type.casefold(), set()).add(
            origin_id
        )

    def remove_damage_resistance(self, damage_type: str, origin_id: str) -> None:
        """Remove one source while retaining any other resistance sources.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.add_damage_resistance("fire", "spell:protection")
        >>> creature.remove_damage_resistance("fire", "spell:protection")
        >>> creature.has_damage_resistance("fire")
        False
        """
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
        """Register a sourced, once-per-turn damage reduction.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_damage_reduction("heavy_armor_master", "feature", DamageReduction("slashing", "1d3"))
        >>> creature.resolve_damage_reduction("slashing", lambda _: 2)
        2
        """
        self.damage_reduction_sources.setdefault(definition_id, {})[origin_id] = (
            reduction
        )

    def remove_damage_reduction(self, definition_id: str, origin_id: str) -> None:
        """Remove a sourced damage reduction.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_damage_reduction("feature", "origin", DamageReduction("fire", "1d4"))
        >>> creature.remove_damage_reduction("feature", "origin")
        >>> creature.resolve_damage_reduction("fire", lambda _: 4)
        0
        """
        sources = self.damage_reduction_sources.get(definition_id)
        if sources is None:
            return
        sources.pop(origin_id, None)
        if not sources:
            self.damage_reduction_sources.pop(definition_id, None)

    def resolve_damage_reduction(self, damage_type: str, roller: DieRoller) -> int:
        """Resolve the active reduction matching a damage type.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_damage_reduction("feature", "origin", DamageReduction("fire", "1d4"))
        >>> (creature.resolve_damage_reduction("fire", lambda _: 3), creature.resolve_damage_reduction("fire", lambda _: 3))
        (3, 0)
        """
        return sum(
            reduction.resolve(roller)
            for sources in self.damage_reduction_sources.values()
            for reduction in tuple(sources.values())[:1]
            if reduction.damage_type == damage_type.casefold()
        )

    def reset_per_turn_modifiers(self) -> None:
        """Restore per-turn sourced defenses for a new turn.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_damage_reduction("feature", "origin", DamageReduction("fire", "1d4"))
        >>> creature.resolve_damage_reduction("fire", lambda _: 3)
        3
        >>> creature.reset_per_turn_modifiers()
        >>> creature.resolve_damage_reduction("fire", lambda _: 2)
        2
        """
        for sources in self.damage_reduction_sources.values():
            for reduction in sources.values():
                reduction.available = True

    def condition_immunities(self) -> frozenset[Condition]:
        """Return intrinsic and temporary condition immunities together.

        >>> stats = CreatureStatistics(condition_immunities=frozenset({Condition.POISONED}))
        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment(), statistics=stats)
        >>> creature.set_condition_immunities("spell", "origin", frozenset({Condition.CHARMED}))
        >>> creature.condition_immunities() == frozenset({Condition.POISONED, Condition.CHARMED})
        True
        """
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
        """Set temporary condition immunities supplied by one source.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_condition_immunities("mind_blank", "cast", frozenset({Condition.CHARMED}))
        >>> Condition.CHARMED in creature.condition_immunities()
        True
        """
        self.condition_immunity_sources.setdefault(definition_id, {})[origin_id] = (
            conditions
        )

    def remove_condition_immunities(self, definition_id: str, origin_id: str) -> None:
        """Remove temporary condition immunities from one source.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_condition_immunities("mind_blank", "cast", frozenset({Condition.CHARMED}))
        >>> creature.remove_condition_immunities("mind_blank", "cast")
        >>> Condition.CHARMED in creature.condition_immunities()
        False
        """
        sources = self.condition_immunity_sources.get(definition_id)
        if sources is None:
            return
        sources.pop(origin_id, None)
        if not sources:
            self.condition_immunity_sources.pop(definition_id, None)

    def set_senses(
        self,
        definition_id: str,
        origin_id: str,
        senses: tuple[tuple[str, int], ...],
    ) -> None:
        """Set senses supplied by one runtime source.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_senses("truesight", "spell", (("truesight", 120),))
        >>> creature.sense_range("truesight")
        120
        """
        self.sense_sources.setdefault(definition_id, {})[origin_id] = senses

    def remove_senses(self, definition_id: str, origin_id: str) -> None:
        """Remove senses supplied by one runtime source.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_senses("truesight", "spell", (("truesight", 120),))
        >>> creature.remove_senses("truesight", "spell")
        >>> creature.has_sense("truesight")
        False
        """
        sources = self.sense_sources.get(definition_id)
        if sources is None:
            return
        sources.pop(origin_id, None)
        if not sources:
            self.sense_sources.pop(definition_id, None)

    def sense_range(self, sense: str) -> int | None:
        """Return the longest intrinsic or granted range for a sense.

        >>> stats = CreatureStatistics(senses=("Darkvision 60 ft.",))
        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment(), statistics=stats)
        >>> creature.set_senses("spell", "origin", (("darkvision", 120),))
        >>> creature.sense_range("darkvision")
        120
        """
        normalized = sense.casefold()
        ranges = [
            feet
            for sources in self.sense_sources.values()
            for granted in sources.values()
            for kind, feet in granted
            if kind == normalized
        ]
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

    def set_roll_modifiers(
        self,
        definition_id: str,
        origin_id: str,
        modifiers: tuple[RollModifier, ...],
    ) -> None:
        """Set roll modifiers supplied by one runtime source.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_roll_modifiers("bless", "cast", (RollModifier("saving_throw", "add", value=1),))
        >>> creature.resolve_roll_modifiers("saving_throw", lambda _: 1)
        1
        """
        self.roll_modifier_sources.setdefault(definition_id, {})[origin_id] = modifiers

    def remove_roll_modifiers(self, definition_id: str, origin_id: str) -> None:
        """Remove roll modifiers supplied by one runtime source.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_roll_modifiers("bless", "cast", (RollModifier("saving_throw", "add", value=1),))
        >>> creature.remove_roll_modifiers("bless", "cast")
        >>> creature.resolve_roll_modifiers("saving_throw", lambda _: 1)
        0
        """
        sources = self.roll_modifier_sources.get(definition_id)
        if sources is None:
            return
        sources.pop(origin_id, None)
        if not sources:
            self.roll_modifier_sources.pop(definition_id, None)

    def resolve_roll_modifiers(
        self, roll: RollKind, roller: DieRoller, ability: str | None = None
    ) -> int:
        """Resolve numeric modifiers matching a roll and optional ability.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> modifier = RollModifier("saving_throw", "add", dice="1d4", ability="wisdom")
        >>> creature.set_roll_modifiers("bless", "cast", (modifier,))
        >>> creature.resolve_roll_modifiers("saving_throw", lambda _: 3, "wisdom")
        3
        """
        return sum(
            modifier.resolve(roller)
            for sources in self.roll_modifier_sources.values()
            for modifiers in tuple(sources.values())[:1]
            for modifier in modifiers
            if modifier.roll == roll
            and modifier.subject == "target"
            and (modifier.ability is None or modifier.ability == ability)
        )

    def roll_mode(self, roll: RollKind, ability: str | None = None) -> D20RollMode:
        """Combine advantage modes matching a roll and optional ability.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_roll_modifiers("dodge", "turn", (RollModifier("saving_throw", "advantage"),))
        >>> creature.roll_mode("saving_throw")
        'advantage'
        """
        return combine_roll_modes(
            *(
                modifier.roll_mode
                for sources in self.roll_modifier_sources.values()
                for modifiers in tuple(sources.values())[:1]
                for modifier in modifiers
                if modifier.roll == roll
                and modifier.subject == "target"
                and (modifier.ability is None or modifier.ability == ability)
                and modifier.roll_mode is not None
            )
        )

    def incoming_attack_roll_mode(
        self, attacker: Creature | None = None
    ) -> D20RollMode:
        """Combine modifiers that apply to attacks against this creature.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> modifier = RollModifier("attack_roll", "advantage", subject="attacks_against_target")
        >>> creature.set_roll_modifiers("faerie_fire", "cast", (modifier,))
        >>> creature.incoming_attack_roll_mode()
        'advantage'
        """
        return combine_roll_modes(
            *(
                modifier.roll_mode
                for sources in self.roll_modifier_sources.values()
                for modifiers in tuple(sources.values())[:1]
                for modifier in modifiers
                if modifier.roll == "attack_roll"
                and modifier.subject == "attacks_against_target"
                and modifier.roll_mode is not None
                and not (
                    attacker is not None
                    and any(
                        attacker.has_sense(sense)
                        for sense in modifier.ignored_by_senses
                    )
                )
            )
        )

    def heal(self, amount: int) -> int:
        """Restore health up to the creature's maximum and return the amount.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.take_damage(8)
        8
        >>> creature.heal(5)
        5
        >>> creature.get_health()
        17
        """
        missing_health = self.get_max_health() - self.get_health()
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
        """Return base AC plus Dexterity and sourced modifiers.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 14, 10, 10, 10, 10, 10), Equipment())
        >>> creature.get_armor_class()
        12
        """
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
        """Set an armor-class modifier supplied by one source.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_armor_class_modifier("shield_of_faith", "cast", 2)
        >>> creature.get_armor_class()
        13
        """
        self.armor_class_modifier_sources.setdefault(definition_id, {})[origin_id] = (
            value
        )

    def remove_armor_class_modifier(self, definition_id: str, origin_id: str) -> None:
        """Remove an armor-class modifier supplied by one source.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_armor_class_modifier("shield_of_faith", "cast", 2)
        >>> creature.remove_armor_class_modifier("shield_of_faith", "cast")
        >>> creature.get_armor_class()
        11
        """
        sources = self.armor_class_modifier_sources.get(definition_id)
        if sources is None:
            return
        sources.pop(origin_id, None)
        if not sources:
            self.armor_class_modifier_sources.pop(definition_id, None)

    def effective_speed_feet(self) -> int:
        """Return movement speed after combining sourced adjustments.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_speed_modifier("slow", "cast", -20)
        >>> creature.effective_speed_feet()
        10
        """
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
        """Set a speed adjustment supplied by one source.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_speed_modifier("longstrider", "cast", 10)
        >>> creature.effective_speed_feet()
        40
        """
        self.speed_modifier_sources.setdefault(definition_id, {})[origin_id] = feet

    def remove_speed_modifier(self, definition_id: str, origin_id: str) -> None:
        """Remove a speed adjustment supplied by one source.

        >>> creature = Creature("hero", "Hero", "", Inventory(), Attributes(20, 1, 14, 12, 10, 10, 10, 10, 10), Equipment())
        >>> creature.set_speed_modifier("longstrider", "cast", 10)
        >>> creature.remove_speed_modifier("longstrider", "cast")
        >>> creature.effective_speed_feet()
        30
        """
        sources = self.speed_modifier_sources.get(definition_id)
        if sources is None:
            return
        sources.pop(origin_id, None)
        if not sources:
            self.speed_modifier_sources.pop(definition_id, None)
