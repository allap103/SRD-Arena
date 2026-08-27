"""Route spell-action dice through the stable execution facade."""


def roll_die(sides: int) -> int:
    """Roll one die through the spell runtime's injectable random source."""

    from .. import spellcasting as spellcasting_facade

    return spellcasting_facade._roll_die(sides)
