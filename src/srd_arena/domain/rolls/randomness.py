"""Provide the explicit random-dice dependency used during combat execution."""

from collections.abc import Callable
from dataclasses import dataclass

from .dice import DieRoller, roll_die

DicePoolRoller = Callable[[int, int], int]


@dataclass(frozen=True)
class DiceRoller:
    """Adapt injectable functions to the complete combat dice contract.

    Supplying only a single-die function keeps every pool roll derived from the
    same source. The optional pool function supports legacy mechanics that
    currently resolve an aggregate total rather than retaining individual dice.

    >>> fixed = DiceRoller(die_roller=lambda _sides: 4)
    >>> (fixed.roll_die(20), fixed.roll_dice(2, 6))
    (4, 8)
    """

    die_roller: DieRoller = roll_die
    pool_roller: DicePoolRoller | None = None

    def roll_die(self, sides: int) -> int:
        """Roll one die through the configured source.

        >>> DiceRoller(die_roller=lambda sides: sides).roll_die(8)
        8
        """

        return self.die_roller(sides)

    def roll_dice(self, count: int, sides: int) -> int:
        """Roll an aggregate pool, deriving it from single dice by default.

        >>> DiceRoller(die_roller=lambda _sides: 3).roll_dice(2, 6)
        6
        >>> DiceRoller(pool_roller=lambda count, sides: count + sides).roll_dice(2, 6)
        8
        """

        if self.pool_roller is not None:
            return self.pool_roller(count, sides)
        return sum(self.roll_die(sides) for _ in range(count))
