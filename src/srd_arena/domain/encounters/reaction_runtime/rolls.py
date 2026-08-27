"""Route reaction dice through the stable, patchable facade."""


def roll_die(sides: int) -> int:
    """Roll one die through the encounter's injectable random source."""

    from .. import reactions as reaction_facade

    return reaction_facade._roll_die(sides)


def roll_dice(count: int, sides: int) -> int:
    """Roll and sum identical dice through the encounter's random source."""

    from .. import reactions as reaction_facade

    return reaction_facade._roll_dice(count, sides)
