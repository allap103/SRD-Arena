from collections.abc import Callable, Collection
from dataclasses import dataclass
import random
from typing import Literal


DieRoller = Callable[[int], int]
D20RollMode = Literal["normal", "advantage", "disadvantage"]


@dataclass(frozen=True)
class DieRollResult:
    sides: int
    rolls: tuple[int, ...]

    @property
    def result(self) -> int:
        return self.rolls[-1]


@dataclass(frozen=True)
class DiceRollResult:
    dice: tuple[DieRollResult, ...]
    modifier: int
    subtotal: int
    total: int


@dataclass(frozen=True)
class D20RollResult:
    mode: D20RollMode
    dice: tuple[int, ...]
    selected_index: int
    modifier: int
    total: int

    @property
    def selected(self) -> int:
        return self.dice[self.selected_index]


@dataclass(frozen=True)
class CheckResult:
    roll: D20RollResult
    target: int
    success: bool


def roll_dice(num_dice, sides):
    total = 0
    for _ in range(num_dice):
        total += roll_die(sides)
    return total


def roll_die(sides):
    """Roll a dice with the given number of sides."""
    return random.randint(1, sides)


def resolve_dice(
    num_dice: int,
    sides: int,
    *,
    modifier: int = 0,
    reroll_values: Collection[int] = (),
    max_rerolls_per_die: int = 0,
    roller: DieRoller = roll_die,
) -> DiceRollResult:
    """Roll a pool, optionally replacing matching results with later rolls."""
    if num_dice < 1:
        raise ValueError("num_dice must be at least 1.")
    if sides < 2:
        raise ValueError("sides must be at least 2.")
    if max_rerolls_per_die < 0:
        raise ValueError("max_rerolls_per_die cannot be negative.")

    reroll_set = frozenset(reroll_values)
    invalid_values = reroll_set.difference(range(1, sides + 1))
    if invalid_values:
        raise ValueError(f"reroll_values contains invalid d{sides} results.")

    dice: list[DieRollResult] = []
    for _ in range(num_dice):
        rolls = [roller(sides)]
        while rolls[-1] in reroll_set and len(rolls) <= max_rerolls_per_die:
            rolls.append(roller(sides))
        dice.append(DieRollResult(sides=sides, rolls=tuple(rolls)))

    resolved_dice = tuple(dice)
    subtotal = sum(die.result for die in resolved_dice)
    return DiceRollResult(
        dice=resolved_dice,
        modifier=modifier,
        subtotal=subtotal,
        total=subtotal + modifier,
    )


def resolve_d20(
    *,
    modifier: int = 0,
    mode: D20RollMode = "normal",
    roller: DieRoller = roll_die,
) -> D20RollResult:
    """Roll a d20, including advantage or disadvantage selection."""
    if mode not in ("normal", "advantage", "disadvantage"):
        raise ValueError(f"Unsupported d20 roll mode: {mode}.")

    dice = tuple(roller(20) for _ in range(1 if mode == "normal" else 2))
    if mode == "advantage":
        selected_index = max(range(len(dice)), key=dice.__getitem__)
    elif mode == "disadvantage":
        selected_index = min(range(len(dice)), key=dice.__getitem__)
    else:
        selected_index = 0

    total = dice[selected_index] + modifier
    return D20RollResult(
        mode=mode,
        dice=dice,
        selected_index=selected_index,
        modifier=modifier,
        total=total,
    )


def resolve_check(roll: D20RollResult, target: int) -> CheckResult:
    """Compare a completed d20 roll with a target."""
    return CheckResult(roll=roll, target=target, success=roll.total >= target)
