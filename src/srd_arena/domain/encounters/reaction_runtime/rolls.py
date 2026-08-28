"""Route reaction dice through the stable, patchable facade."""


def roll_die(sides: int) -> int:
    """Roll one die through the encounter's injectable random source.

    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.reactions._roll_die", return_value=3
    ... ):
    ...     roll_die(6)
    3
    """

    from .. import reactions as reaction_facade

    return reaction_facade._roll_die(sides)


def roll_dice(count: int, sides: int) -> int:
    """Roll and sum identical dice through the encounter's random source.

    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.reactions._roll_dice", return_value=9
    ... ):
    ...     roll_dice(2, 6)
    9
    """

    from .. import reactions as reaction_facade

    return reaction_facade._roll_dice(count, sides)
