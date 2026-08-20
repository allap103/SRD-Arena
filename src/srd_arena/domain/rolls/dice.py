from collections.abc import Callable, Collection
from dataclasses import dataclass
import random
from typing import Generic, Literal, TypeVar


DieRoller = Callable[[int], int]
D20RollMode = Literal["normal", "advantage", "disadvantage"]


def combine_roll_modes(*modes: D20RollMode) -> D20RollMode:
    has_advantage = "advantage" in modes
    has_disadvantage = "disadvantage" in modes
    if has_advantage == has_disadvantage:
        return "normal"
    return "advantage" if has_advantage else "disadvantage"
RollResultT = TypeVar("RollResultT")


@dataclass(frozen=True)
class DieRollResult:
    sides: int
    rolls: tuple[int, ...]

    @property
    def result(self) -> int:
        return self.rolls[-1]


@dataclass(frozen=True)
class DieReplacement:
    die_index: int
    previous: int
    replacement: int


@dataclass(frozen=True)
class DicePoolResult:
    dice: tuple[DieRollResult, ...]
    modifier: int
    subtotal: int
    total: int
    replacements: tuple[DieReplacement, ...] = ()


@dataclass(frozen=True)
class D20PoolResult:
    dice: tuple[int, ...]


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


@dataclass(frozen=True)
class RollResolution(Generic[RollResultT]):
    attempts: tuple[RollResultT, ...]
    selected_attempt: int
    reason: str

    @property
    def selected(self) -> RollResultT:
        return self.attempts[self.selected_attempt]


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
) -> DicePoolResult:
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
    """Replace selected dice once, using every replacement even if it is worse."""
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
    """Create a fresh attempt with the same dice and modifier as a pool."""
    dice = tuple(
        DieRollResult(sides=die.sides, rolls=(roller(die.sides),))
        for die in pool.dice
    )
    return _dice_pool_result(dice, modifier=pool.modifier)


def resolve_roll_attempts(
    attempts: Collection[RollResultT],
    selected_attempt: int,
    *,
    reason: str,
) -> RollResolution[RollResultT]:
    """Record the choice among complete roll attempts."""
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
    """Roll a d20, including advantage or disadvantage selection."""
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
    """Roll an unresolved pool of d20s."""
    if num_dice < 1:
        raise ValueError("num_dice must be at least 1.")
    return D20PoolResult(dice=tuple(roller(20) for _ in range(num_dice)))


def extend_d20_pool(
    pool: D20PoolResult,
    num_dice: int = 1,
    *,
    roller: DieRoller = roll_die,
) -> D20PoolResult:
    """Add d20s to an unresolved pool without selecting among them."""
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
    """Select one die from a d20 pool and apply the roll modifier."""
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
    """Compare a completed d20 roll with a target."""
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
