"""Provide saving throws support for the rolls package."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from ..effects.modifiers import RollKind
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
    """Define the saving throw creature contract."""

    attributes: Any

    def get_modifier(self, attribute_value: int) -> int: ...

    def resolve_roll_modifiers(
        self, roll: RollKind, roller: DieRoller, ability: str | None = None
    ) -> int: ...

    def roll_mode(self, roll: RollKind, ability: str | None = None) -> D20RollMode: ...


@dataclass(frozen=True)
class SavingThrowModifiers:
    """Represent a saving throw modifiers."""

    ability: int
    proficiency: int
    other: int = 0

    @property
    def total(self) -> int:
        return self.ability + self.proficiency + self.other


@dataclass(frozen=True)
class SavingThrowResult:
    """Represent a saving throw result."""

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
    """Resolve an creature's saving throw against a target."""
    ability_score = getattr(creature.attributes, ability)
    ability_modifier = creature.get_modifier(ability_score)
    explicit_bonus = _explicit_saving_throw_bonus(creature, ability)
    proficient = explicit_bonus is not None or _is_save_proficient(creature, ability)
    proficiency_modifier = (
        explicit_bonus - ability_modifier
        if explicit_bonus is not None
        else int(creature.attributes.proficiency_bonus)
        if proficient
        else 0
    )
    resolve_modifiers = getattr(creature, "resolve_roll_modifiers", None)
    sourced_modifier = (
        (
            resolve_modifiers("saving_throw", roller, ability)
            if callable(resolve_modifiers)
            else 0
        )
        if sourced_modifier_override is None
        else sourced_modifier_override
    )
    modifiers = SavingThrowModifiers(
        ability=ability_modifier,
        proficiency=proficiency_modifier,
        other=other_modifier + sourced_modifier,
    )
    roll = resolve_d20(
        modifier=modifiers.total,
        mode=combine_roll_modes(
            mode,
            (
                _sourced_roll_mode(creature, ability)
                if sourced_mode_override is None
                else sourced_mode_override
            ),
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


def _sourced_roll_mode(
    creature: SavingThrowCreature,
    ability: Ability,
) -> D20RollMode:
    roll_mode = getattr(creature, "roll_mode", None)
    return roll_mode("saving_throw", ability) if callable(roll_mode) else "normal"


def reroll_saving_throw(
    creature: SavingThrowCreature,
    original: SavingThrowResult,
    *,
    bonus_modifier: int = 0,
    mode: D20RollMode = "normal",
    roller: DieRoller = roll_die,
) -> SavingThrowResult:
    """Repeat a save against the same target, retaining its existing modifiers."""
    return resolve_saving_throw(
        creature,
        original.ability,
        original.check.target,
        mode=mode,
        other_modifier=original.modifiers.other + bonus_modifier,
        roller=roller,
        automatic_failure_reasons=original.automatic_failure_reasons,
    )


def _is_save_proficient(creature: SavingThrowCreature, ability: Ability) -> bool:
    proficiencies = getattr(creature.attributes, "proficiencies", {})
    if not isinstance(proficiencies, dict):
        return False
    saving_throws = proficiencies.get("saving_throws", [])
    if not isinstance(saving_throws, list):
        return False
    aliases = {
        "strength": "str",
        "dexterity": "dex",
        "constitution": "con",
        "intelligence": "int",
        "wisdom": "wis",
        "charisma": "cha",
    }
    normalized = {str(item).casefold() for item in saving_throws}
    return ability in normalized or aliases[ability] in normalized


def _explicit_saving_throw_bonus(
    creature: SavingThrowCreature,
    ability: Ability,
) -> int | None:
    statistics = getattr(creature, "statistics", None)
    bonuses = getattr(statistics, "saving_throw_bonuses", {})
    if not isinstance(bonuses, dict):
        return None
    value = bonuses.get(ability)
    return value if isinstance(value, int) else None
