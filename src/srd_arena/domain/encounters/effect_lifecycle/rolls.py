"""Route lifecycle dice through the encounter runtime's patchable roll seam."""


def roll_die(sides: int) -> int:
    """Roll through ``ongoing_effects._roll_die`` at call time.

    The indirection preserves both the historical ongoing-effect monkeypatch
    path and the broader ``encounter.roll_die`` seam used by encounter tests.
    """

    from .. import ongoing_effects as lifecycle_facade

    return lifecycle_facade._roll_die(sides)
