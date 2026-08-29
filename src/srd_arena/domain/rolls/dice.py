"""Resolve dice pools while retaining enough detail for reactions and clients."""

import random
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Literal

DieRoller = Callable[[int], int]
D20RollMode = Literal["normal", "advantage", "disadvantage"]


def combine_roll_modes(*modes: D20RollMode) -> D20RollMode:
    """Combine advantage and disadvantage using cancellation rules.

    >>> combine_roll_modes("advantage")
    'advantage'
    >>> combine_roll_modes("advantage", "disadvantage")
    'normal'
    """

    has_advantage = "advantage" in modes
    has_disadvantage = "disadvantage" in modes
    if has_advantage == has_disadvantage:
        return "normal"
    return "advantage" if has_advantage else "disadvantage"


@dataclass(frozen=True)
class DieRollResult:
    """Retain one die's original result and any ordered replacements."""

    sides: int
    rolls: tuple[int, ...]

    @property
    def result(self) -> int:
        """Return the final result after any replacements.

        >>> DieRollResult(sides=6, rolls=(1, 5)).result
        5
        """
        return self.rolls[-1]


@dataclass(frozen=True)
class DieReplacement:
    """Record which die result a reroll replaced in a resolved pool."""

    die_index: int
    previous: int
    replacement: int


@dataclass(frozen=True)
class DicePoolResult:
    """Record every die, modifier, and replacement contributing to a total."""

    dice: tuple[DieRollResult, ...]
    modifier: int
    subtotal: int
    total: int
    replacements: tuple[DieReplacement, ...] = ()


@dataclass(frozen=True)
class D20PoolResult:
    """Hold unresolved d20 values until a rule selects one of them."""

    dice: tuple[int, ...]


@dataclass(frozen=True)
class D20RollResult:
    """Record a selected d20 and the roll mode and modifier that produced its total."""

    mode: D20RollMode
    dice: tuple[int, ...]
    selected_index: int
    modifier: int
    total: int

    @property
    def selected(self) -> int:
        """Return the selected d20 value.

        >>> D20RollResult("advantage", (7, 16), 1, 3, 19).selected
        16
        """
        return self.dice[self.selected_index]


@dataclass(frozen=True)
class CheckResult:
    """Record whether a completed d20 roll met a target number."""

    roll: D20RollResult
    target: int
    success: bool


@dataclass(frozen=True)
class RollResolution[RollResultT]:
    """Retain multiple complete attempts and the rule-selected final attempt."""

    attempts: tuple[RollResultT, ...]
    selected_attempt: int
    reason: str

    @property
    def selected(self) -> RollResultT:
        """Return the chosen attempt.

        >>> RollResolution(("first", "second"), 1, "reroll").selected
        'second'
        """
        return self.attempts[self.selected_attempt]


def roll_die(sides: int) -> int:
    """Roll one die with the given number of sides.

    >>> 1 <= roll_die(6) <= 6
    True
    """
    return random.randint(1, sides)


def resolve_dice(
    num_dice: int,
    sides: int,
    *,
    modifier: int = 0,
    reroll_values: Collection[int] = (),
    max_rerolls_per_die: int = 0,
    roller: DieRoller = roll_die,
) -> DicePoolResult:
    """Roll a pool, optionally replacing matching results with later rolls.

    >>> results = iter((1, 4, 3))
    >>> pool = resolve_dice(2, 6, reroll_values=(1,), max_rerolls_per_die=1,
    ...                     roller=lambda _: next(results))
    >>> (pool.subtotal, pool.total, len(pool.replacements))
    (7, 7, 1)
    """
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
    replacements: list[DieReplacement] = []
    for die_index in range(num_dice):
        rolls = [roller(sides)]
        while rolls[-1] in reroll_set and len(rolls) <= max_rerolls_per_die:
            previous = rolls[-1]
            rolls.append(roller(sides))
            replacements.append(
                DieReplacement(
                    die_index=die_index,
                    previous=previous,
                    replacement=rolls[-1],
                )
            )
        dice.append(DieRollResult(sides=sides, rolls=tuple(rolls)))

    return _dice_pool_result(
        tuple(dice),
        modifier=modifier,
        replacements=tuple(replacements),
    )


def reroll_dice(
    pool: DicePoolResult,
    die_indices: Collection[int],
    *,
    roller: DieRoller = roll_die,
) -> DicePoolResult:
    """Replace selected dice once, even when a replacement is worse.

    >>> values = iter((5, 4))
    >>> pool = resolve_dice(2, 6, roller=lambda _: next(values))
    >>> reroll_dice(pool, (0,), roller=lambda _: 2).total
    6
    """
    indices = tuple(die_indices)
    if len(indices) != len(set(indices)):
        raise ValueError("die_indices cannot contain duplicates.")
    if any(index < 0 or index >= len(pool.dice) for index in indices):
        raise IndexError("die_indices contains an index outside the dice pool.")

    dice = list(pool.dice)
    replacements = list(pool.replacements)
    for index in indices:
        die = dice[index]
        replacement = roller(die.sides)
        replacements.append(
            DieReplacement(
                die_index=index,
                previous=die.result,
                replacement=replacement,
            )
        )
        dice[index] = DieRollResult(
            sides=die.sides,
            rolls=(*die.rolls, replacement),
        )

    return _dice_pool_result(
        tuple(dice),
        modifier=pool.modifier,
        replacements=tuple(replacements),
    )


def reroll_dice_pool(
    pool: DicePoolResult,
    *,
    roller: DieRoller = roll_die,
) -> DicePoolResult:
    """Create a fresh attempt with the same dice and modifier as a pool.

    >>> values = iter((2, 3))
    >>> pool = resolve_dice(2, 6, modifier=1, roller=lambda _: next(values))
    >>> reroll_dice_pool(pool, roller=lambda _: 6).total
    13
    """
    dice = tuple(
        DieRollResult(sides=die.sides, rolls=(roller(die.sides),)) for die in pool.dice
    )
    return _dice_pool_result(dice, modifier=pool.modifier)


def resolve_roll_attempts[RollResultT](
    attempts: Collection[RollResultT],
    selected_attempt: int,
    *,
    reason: str,
) -> RollResolution[RollResultT]:
    """Record the choice among complete roll attempts.

    >>> resolve_roll_attempts((10, 17), 1, reason="Lucky").selected
    17
    """
    resolved_attempts = tuple(attempts)
    if not resolved_attempts:
        raise ValueError("attempts must contain at least one roll.")
    if selected_attempt < 0 or selected_attempt >= len(resolved_attempts):
        raise IndexError("selected_attempt is outside the available attempts.")
    return RollResolution(
        attempts=resolved_attempts,
        selected_attempt=selected_attempt,
        reason=reason,
    )


def resolve_d20(
    *,
    modifier: int = 0,
    mode: D20RollMode = "normal",
    roller: DieRoller = roll_die,
) -> D20RollResult:
    """Roll a d20, including advantage or disadvantage selection.

    >>> values = iter((8, 15))
    >>> roll = resolve_d20(modifier=2, mode="advantage", roller=lambda _: next(values))
    >>> (roll.selected, roll.total)
    (15, 17)
    """
    if mode not in ("normal", "advantage", "disadvantage"):
        raise ValueError(f"Unsupported d20 roll mode: {mode}.")

    pool = roll_d20_pool(1 if mode == "normal" else 2, roller=roller)
    if mode == "advantage":
        selected_index = _highest_d20_index(pool)
    elif mode == "disadvantage":
        selected_index = _lowest_d20_index(pool)
    else:
        selected_index = 0

    return select_d20(
        pool,
        selected_index=selected_index,
        modifier=modifier,
        mode=mode,
    )


def roll_d20_pool(
    num_dice: int = 1,
    *,
    roller: DieRoller = roll_die,
) -> D20PoolResult:
    """Roll an unresolved pool of d20s.

    >>> roll_d20_pool(2, roller=lambda _: 11)
    D20PoolResult(dice=(11, 11))
    """
    if num_dice < 1:
        raise ValueError("num_dice must be at least 1.")
    return D20PoolResult(dice=tuple(roller(20) for _ in range(num_dice)))


def extend_d20_pool(
    pool: D20PoolResult,
    num_dice: int = 1,
    *,
    roller: DieRoller = roll_die,
) -> D20PoolResult:
    """Add d20s to an unresolved pool without selecting among them.

    >>> extend_d20_pool(D20PoolResult((4,)), 2, roller=lambda _: 12)
    D20PoolResult(dice=(4, 12, 12))
    """
    if num_dice < 1:
        raise ValueError("num_dice must be at least 1.")
    return D20PoolResult(
        dice=(*pool.dice, *(roller(20) for _ in range(num_dice))),
    )


def select_d20(
    pool: D20PoolResult,
    selected_index: int,
    *,
    modifier: int = 0,
    mode: D20RollMode = "normal",
) -> D20RollResult:
    """Select one die from a d20 pool and apply the roll modifier.

    >>> selected = select_d20(D20PoolResult((5, 14)), 1, modifier=3)
    >>> (selected.selected, selected.total)
    (14, 17)
    """
    if selected_index < 0 or selected_index >= len(pool.dice):
        raise IndexError("selected_index is outside the d20 pool.")
    selected = pool.dice[selected_index]
    return D20RollResult(
        mode=mode,
        dice=pool.dice,
        selected_index=selected_index,
        modifier=modifier,
        total=selected + modifier,
    )


def resolve_check(roll: D20RollResult, target: int) -> CheckResult:
    """Compare a completed d20 roll with a target.

    >>> roll = select_d20(D20PoolResult((12,)), 0, modifier=3)
    >>> resolve_check(roll, 15).success
    True
    """
    return CheckResult(roll=roll, target=target, success=roll.total >= target)


def _dice_pool_result(
    dice: tuple[DieRollResult, ...],
    *,
    modifier: int,
    replacements: tuple[DieReplacement, ...] = (),
) -> DicePoolResult:
    subtotal = sum(die.result for die in dice)
    return DicePoolResult(
        dice=dice,
        modifier=modifier,
        subtotal=subtotal,
        total=subtotal + modifier,
        replacements=replacements,
    )


def _highest_d20_index(pool: D20PoolResult) -> int:
    return max(range(len(pool.dice)), key=pool.dice.__getitem__)


def _lowest_d20_index(pool: D20PoolResult) -> int:
    return min(range(len(pool.dice)), key=pool.dice.__getitem__)
