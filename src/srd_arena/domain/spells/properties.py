"""Derive convenient spell properties from metadata and capability scaling."""

from .definitions import Spell


def spell_supports_higher_level(spell: Spell) -> bool:
    """Return whether resource-level scaling gives the spell an upcast benefit.

    >>> from srd_arena.domain.capabilities import (
    ...     AutomaticResolution, CapabilityDefinition, CapabilityScaling,
    ...     CapabilityTarget, Outcome, ScalingIncrement,
    ... )
    >>> definition = CapabilityDefinition(
    ...     CapabilityTarget("self"), AutomaticResolution(Outcome()),
    ...     scaling=(CapabilityScaling(
    ...         "resource_level", per_level=(ScalingIncrement("damage_dice", "1d6"),)
    ...     ),),
    ... )
    >>> spell_supports_higher_level(
    ...     Spell("fireball", "Fireball", "XPHB", 3, definition=definition)
    ... )
    True
    """

    if spell.definition is not None:
        return any(
            scaling.basis == "resource_level" and scaling.per_level
            for scaling in spell.definition.scaling
        )
    return False


def spell_duration_rounds(spell: Spell) -> int | None:
    """Return the spell metadata duration converted to encounter rounds.

    >>> from .metadata import SpellDuration
    >>> spell = Spell(
    ...     "bless", "Bless", "XPHB", 1,
    ...     durations=(SpellDuration("timed", 1, "minute"),),
    ... )
    >>> spell_duration_rounds(spell)
    10
    """
    rounds_per_unit = {
        "round": 1,
        "minute": 10,
        "hour": 600,
        "day": 14_400,
    }
    for duration in spell.durations:
        if duration.unit is not None and duration.amount is not None:
            multiplier = rounds_per_unit.get(duration.unit)
            if multiplier is not None:
                return duration.amount * multiplier
    return None
