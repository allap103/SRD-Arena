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
    creature: Creature
    target_ref: str
    target_label: str
    target_conditions: tuple[str, ...] = ()
    automatic_save_failures: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def automatic_failure_reasons(self, ability: str) -> tuple[str, ...]:
        return self.automatic_save_failures.get(ability, ())


@dataclass(frozen=True)
class SpellActionContext:
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
    automatic_critical_providers: dict[str, tuple[str, ...]] = field(
        default_factory=dict
    )
    cast_level: int | None = None
    save_roll_modes: dict[str, D20RollMode] = field(default_factory=dict)
    area_targets_around: Callable[[str, int], tuple[SpellTargetContext, ...]] | None = (
        None
    )
    healing_allocations: dict[str, int] = field(default_factory=dict)
