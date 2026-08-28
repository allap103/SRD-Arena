"""Route lifecycle dice through the encounter runtime's patchable roll seam."""


def roll_die(sides: int) -> int:
    """Roll through ``ongoing_effects._roll_die`` at call time.

    The indirection preserves both the historical ongoing-effect monkeypatch
    path and the broader ``encounter.roll_die`` seam used by encounter tests.

    >>> from unittest.mock import patch
    >>> with patch(
    ...     "srd_arena.domain.encounters.ongoing_effects._roll_die",
    ...     return_value=5,
    ... ):
    ...     roll_die(8)
    5
    """

    from .. import ongoing_effects as lifecycle_facade

    return lifecycle_facade._roll_die(sides)
