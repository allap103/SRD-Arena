"""Dice seams shared by stat-block action resolvers."""

from __future__ import annotations


def roll_die(sides: int) -> int:
    """Roll through the encounter module so existing test seams remain stable.

    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.encounter.roll_die", return_value=4
    ... ):
    ...     roll_die(6)
    4
    """
    from ... import encounter as encounter_module

    return encounter_module.roll_die(sides)


def roll_dice(count: int, sides: int) -> int:
    """Roll damage through the encounter module's replaceable roller.

    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.encounter.roll_dice", return_value=7
    ... ):
    ...     roll_dice(2, 6)
    7
    """
    from ... import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)
