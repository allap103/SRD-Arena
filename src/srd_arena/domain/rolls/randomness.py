"""Provide the explicit random-dice dependency used during combat execution."""

from dataclasses import dataclass

from .dice import DieRoller, roll_die


@dataclass(frozen=True)
class DiceRoller:
    """Provide combat resolution with one injectable source of individual dice.

    >>> fixed = DiceRoller(die_roller=lambda _sides: 4)
    >>> fixed.roll_die(20)
    4
    """

    die_roller: DieRoller = roll_die

    def roll_die(self, sides: int) -> int:
        """Roll one die through the configured source.

        >>> DiceRoller(die_roller=lambda sides: sides).roll_die(8)
        8
        """

        return self.die_roller(sides)
