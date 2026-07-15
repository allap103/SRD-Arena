from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .dice import (
    CheckResult,
    D20RollMode,
    DieRoller,
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


class SavingThrowActor(Protocol):
    attributes: object

    def get_modifier(self, attribute_value: int) -> int: ...


@dataclass(frozen=True)
class SavingThrowModifiers:
    ability: int
    proficiency: int
    other: int = 0

    @property
    def total(self) -> int:
        return self.ability + self.proficiency + self.other


@dataclass(frozen=True)
class SavingThrowResult:
    ability: Ability
    proficient: bool
    modifiers: SavingThrowModifiers
    check: CheckResult


def resolve_saving_throw(
    actor: SavingThrowActor,
    ability: Ability,
    target: int,
    *,
    mode: D20RollMode = "normal",
    other_modifier: int = 0,
    roller: DieRoller = roll_die,
) -> SavingThrowResult:
    """Resolve an actor's saving throw against a target."""
    ability_score = getattr(actor.attributes, ability)
    ability_modifier = actor.get_modifier(ability_score)
    proficient = _is_save_proficient(actor, ability)
    proficiency_modifier = (
        int(getattr(actor.attributes, "proficiency_bonus")) if proficient else 0
    )
    modifiers = SavingThrowModifiers(
        ability=ability_modifier,
        proficiency=proficiency_modifier,
        other=other_modifier,
    )
    roll = resolve_d20(modifier=modifiers.total, mode=mode, roller=roller)
    return SavingThrowResult(
        ability=ability,
        proficient=proficient,
        modifiers=modifiers,
        check=resolve_check(roll, target),
    )


def reroll_saving_throw(
    actor: SavingThrowActor,
    original: SavingThrowResult,
    *,
    bonus_modifier: int = 0,
    mode: D20RollMode = "normal",
    roller: DieRoller = roll_die,
) -> SavingThrowResult:
    """Repeat a save against the same target, retaining its existing modifiers."""
    return resolve_saving_throw(
        actor,
        original.ability,
        original.check.target,
        mode=mode,
        other_modifier=original.modifiers.other + bonus_modifier,
        roller=roller,
    )


def _is_save_proficient(actor: SavingThrowActor, ability: Ability) -> bool:
    proficiencies = getattr(actor.attributes, "proficiencies", {})
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
