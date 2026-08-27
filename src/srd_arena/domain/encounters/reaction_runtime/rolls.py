"""Route reaction dice through the stable, patchable facade."""


def roll_die(sides: int) -> int:
    from .. import reactions as reaction_facade

    return reaction_facade._roll_die(sides)


def roll_dice(count: int, sides: int) -> int:
    from .. import reactions as reaction_facade

    return reaction_facade._roll_dice(count, sides)
