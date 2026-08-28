"""Route spell-action dice through the stable execution facade."""


def roll_die(sides: int) -> int:
    """Roll one die through the spell runtime's injectable random source.

    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.spellcasting._roll_die",
    ...     return_value=4,
    ... ):
    ...     roll_die(6)
    4
    """

    from .. import spellcasting as spellcasting_facade

    return spellcasting_facade._roll_die(sides)
