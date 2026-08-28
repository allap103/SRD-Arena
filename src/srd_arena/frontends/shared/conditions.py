"""Extract display-ready condition names from observed creature state."""

from srd_arena.application.api import CreatureObservation


def effective_condition_names(creature: CreatureObservation) -> tuple[str, ...]:
    """Return the effective conditions calculated by the game engine.

    >>> from types import SimpleNamespace
    >>> effective_condition_names(
    ...     SimpleNamespace(effective_conditions=("stunned", "incapacitated"))
    ... )
    ('stunned', 'incapacitated')
    """

    return creature.effective_conditions
