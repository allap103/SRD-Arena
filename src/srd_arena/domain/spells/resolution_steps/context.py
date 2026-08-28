"""Inputs supplied to the spell-resolution coordinator."""

from collections.abc import Callable
from dataclasses import dataclass, field

from ...creatures import Creature
from ...geometry import AreaOfEffect
from ...rolls.dice import D20RollMode
from ..definitions import Spell

DieRoller = Callable[[int], int]


@dataclass(frozen=True)
class SpellTargetContext:
    """Supply one target and its encounter-derived facts to spell resolution."""

    creature: Creature
    target_ref: str
    target_label: str
    target_conditions: tuple[str, ...] = ()
    automatic_save_failures: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def automatic_failure_reasons(self, ability: str) -> tuple[str, ...]:
        """Return condition-derived automatic save failures for an ability.

        >>> from srd_arena.domain.creatures import Attributes, Equipment, Inventory
        >>> creature = Creature("hero", "Hero", "", Inventory(),
        ...     Attributes(10, 1, 10, 10, 10, 10, 10, 10, 10), Equipment())
        >>> target = SpellTargetContext(creature, "hero", "Hero",
        ...     automatic_save_failures={"dexterity": ("stunned",)})
        >>> target.automatic_failure_reasons("dexterity")
        ('stunned',)
        >>> target.automatic_failure_reasons("wisdom")
        ()
        """
        return self.automatic_save_failures.get(ability, ())


@dataclass(frozen=True)
class SpellActionContext:
    """Supply one spell invocation with caster, targets, choices, and rule queries.

    The encounter assembles this immutable boundary object before resolution so
    spell code does not reach back into mutable encounter state.
    """

    creature: Creature
    spell: Spell
    target: SpellTargetContext
    current_round: int
    targets: tuple[SpellTargetContext, ...] = ()
    area: AreaOfEffect | None = None
    source_ref: str = "player"
    roller: DieRoller | None = None
    selected_condition: str | None = None
    selected_damage_type: str | None = None
    selected_ability: str | None = None
    attack_roll_modes: dict[str, D20RollMode] = field(default_factory=dict)
    attack_roll_modifiers: dict[str, int] = field(default_factory=dict)
    attack_roll_modifier_for: Callable[[str], int] | None = None
    target_armor_classes: dict[str, int] = field(default_factory=dict)
    damage_roll_modifier: int = 0
    damage_roll_modifier_for: Callable[[], int] | None = None
    automatic_critical_providers: dict[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    cast_level: int | None = None
    save_roll_modes: dict[str, D20RollMode] = field(default_factory=dict)
    save_roll_modifiers: dict[str, int] = field(default_factory=dict)
    save_roll_modifier_for: Callable[[str, str], int] | None = None
    save_sourced_roll_modes: dict[str, D20RollMode] = field(default_factory=dict)
    save_sourced_roll_mode_for: Callable[[str, str], D20RollMode] | None = None
    area_targets_around: Callable[[str, int], tuple[SpellTargetContext, ...]] | None = (
        None
    )
    healing_allocations: dict[str, int] = field(default_factory=dict)
