"""Provide the explicit random-dice dependency used during combat execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from random import Random

from .dice import DieRoller, roll_die


@dataclass(frozen=True)
class DiceRoller:
    """Provide combat resolution with one injectable source of individual dice.

    >>> fixed = DiceRoller(die_roller=lambda _sides: 4)
    >>> fixed.roll_die(20)
    4
    """

    die_roller: DieRoller = roll_die
    _restart: Callable[[], DiceRoller] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    @classmethod
    def seeded(cls, seed: int) -> DiceRoller:
        """Create an isolated reproducible dice stream.

        Recreating the stream through :meth:`restarted` begins the same
        sequence again without changing Python's process-wide random state.

        >>> first = DiceRoller.seeded(42)
        >>> opening = tuple(first.roll_die(20) for _ in range(3))
        >>> restarted = first.restarted()
        >>> tuple(restarted.roll_die(20) for _ in range(3)) == opening
        True
        """

        generator = Random(seed)
        return cls(
            die_roller=lambda sides: generator.randint(1, sides),
            _restart=lambda: cls.seeded(seed),
        )

    def roll_die(self, sides: int) -> int:
        """Roll one die through the configured source.

        >>> DiceRoller(die_roller=lambda sides: sides).roll_die(8)
        8
        """

        return self.die_roller(sides)

    def restarted(self) -> DiceRoller:
        """Return a dice source rewound to its initial state when supported.

        Ordinary injected rollers are returned unchanged because they do not
        advertise restart semantics. Seeded rollers recreate their private
        random-number generator.

        >>> fixed = DiceRoller(die_roller=lambda _sides: 4)
        >>> fixed.restarted() is fixed
        True
        """

        return self._restart() if self._restart is not None else self
