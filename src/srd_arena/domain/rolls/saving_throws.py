"""Resolve saving throws from creature statistics and active rule modifiers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .dice import (
    CheckResult,
    D20RollMode,
    DieRoller,
    combine_roll_modes,
    resolve_check,
    resolve_d20,
    roll_die,
)

Ability = Literal[
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
]


class SavingThrowCreature(Protocol):
    """Expose only intrinsic values required to resolve a saving throw."""

    def get_modifier(self, attribute_value: int) -> int:
        """Return the rules modifier associated with an ability score."""

        ...

    def saving_throw_ability_score(self, ability: Ability) -> int:
        """Return the score associated with the selected saving-throw ability."""

        ...

    @property
    def saving_throw_proficiency_bonus(self) -> int:
        """Return the proficiency contribution available to proficient saves."""

        ...

    def is_saving_throw_proficient(self, ability: Ability) -> bool:
        """Return whether the creature is proficient in the selected save."""

        ...

    def explicit_saving_throw_bonus(self, ability: Ability) -> int | None:
        """Return an authored stat-block save total when present."""

        ...


@dataclass(frozen=True)
class SavingThrowModifiers:
    """Separate ability, proficiency, and situational contributions to a save."""

    ability: int
    proficiency: int
    other: int = 0

    @property
    def total(self) -> int:
        """Return the combined saving-throw modifier.

        >>> SavingThrowModifiers(ability=3, proficiency=2, other=1).total
        6
        """
        return self.ability + self.proficiency + self.other


@dataclass(frozen=True)
class SavingThrowResult:
    """Record a saving throw's inputs, roll, outcome, and forced-failure reasons."""

    ability: Ability
    proficient: bool
    modifiers: SavingThrowModifiers
    check: CheckResult
    automatic_failure_reasons: tuple[str, ...] = ()


def resolve_saving_throw(
    creature: SavingThrowCreature,
    ability: Ability,
    target: int,
    *,
    mode: D20RollMode = "normal",
    other_modifier: int = 0,
    sourced_modifier_override: int | None = None,
    sourced_mode_override: D20RollMode | None = None,
    roller: DieRoller = roll_die,
    automatic_failure_reasons: tuple[str, ...] = (),
) -> SavingThrowResult:
    """Resolve a creature's saving throw against a difficulty class.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     get_modifier=lambda score: (score - 10) // 2,
    ...     saving_throw_ability_score=lambda ability: 14,
    ...     saving_throw_proficiency_bonus=2,
    ...     is_saving_throw_proficient=lambda ability: False,
    ...     explicit_saving_throw_bonus=lambda ability: None,
    ... )
    >>> result = resolve_saving_throw(
    ...     creature, "dexterity", 13, roller=lambda sides: 12
    ... )
    >>> (result.modifiers.total, result.check.total if hasattr(result.check, "total") else result.check.roll.total, result.check.success)
    (2, 14, True)
    """
    ability_score = creature.saving_throw_ability_score(ability)
    ability_modifier = creature.get_modifier(ability_score)
    explicit_bonus = creature.explicit_saving_throw_bonus(ability)
    proficient = explicit_bonus is not None or creature.is_saving_throw_proficient(
        ability
    )
    proficiency_modifier = (
        explicit_bonus - ability_modifier
        if explicit_bonus is not None
        else creature.saving_throw_proficiency_bonus
        if proficient
        else 0
    )
    sourced_modifier = sourced_modifier_override or 0
    modifiers = SavingThrowModifiers(
        ability=ability_modifier,
        proficiency=proficiency_modifier,
        other=other_modifier + sourced_modifier,
    )
    roll = resolve_d20(
        modifier=modifiers.total,
        mode=combine_roll_modes(
            mode,
            sourced_mode_override or "normal",
        ),
        roller=roller,
    )
    check = resolve_check(roll, target)
    if automatic_failure_reasons:
        check = CheckResult(roll=check.roll, target=check.target, success=False)
    return SavingThrowResult(
        ability=ability,
        proficient=proficient,
        modifiers=modifiers,
        check=check,
        automatic_failure_reasons=automatic_failure_reasons,
    )


def reroll_saving_throw(
    creature: SavingThrowCreature,
    original: SavingThrowResult,
    *,
    bonus_modifier: int = 0,
    mode: D20RollMode = "normal",
    roller: DieRoller = roll_die,
) -> SavingThrowResult:
    """Repeat a save against the same target, retaining its existing modifiers.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     get_modifier=lambda score: (score - 10) // 2,
    ...     saving_throw_ability_score=lambda ability: 10,
    ...     saving_throw_proficiency_bonus=2,
    ...     is_saving_throw_proficient=lambda ability: False,
    ...     explicit_saving_throw_bonus=lambda ability: None,
    ... )
    >>> original = resolve_saving_throw(
    ...     creature, "wisdom", 15, roller=lambda sides: 5
    ... )
    >>> rerolled = reroll_saving_throw(
    ...     creature, original, bonus_modifier=1, roller=lambda sides: 20
    ... )
    >>> (original.check.success, rerolled.modifiers.total, rerolled.check.success)
    (False, 1, True)
    """
    return resolve_saving_throw(
        creature,
        original.ability,
        original.check.target,
        mode=mode,
        other_modifier=original.modifiers.other + bonus_modifier,
        roller=roller,
        automatic_failure_reasons=original.automatic_failure_reasons,
    )
