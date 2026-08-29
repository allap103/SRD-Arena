"""Pure combat rules that derive attack behavior from encounter geometry."""

from srd_arena.domain.geometry import Position, grid_distance_between
from srd_arena.domain.rolls.dice import D20RollMode


def proximity_attack_roll_mode(
    attack_type: str,
    attacker_position: Position | None,
    nearby_opponent_positions: tuple[Position, ...],
) -> D20RollMode:
    """Return disadvantage for a ranged attack made beside an opponent.

    >>> proximity_attack_roll_mode(
    ...     "ranged", Position(0, 0), (Position(1, 1),)
    ... )
    'disadvantage'
    >>> proximity_attack_roll_mode(
    ...     "melee", Position(0, 0), (Position(1, 1),)
    ... )
    'normal'
    >>> proximity_attack_roll_mode("ranged", None, (Position(1, 1),))
    'normal'
    """

    if attack_type != "ranged" or attacker_position is None:
        return "normal"
    if any(
        grid_distance_between(attacker_position, position) == 1
        for position in nearby_opponent_positions
    ):
        return "disadvantage"
    return "normal"
