"""Derive convenient spell properties from metadata and capability scaling."""

from .definitions import Spell


def spell_supports_higher_level(spell: Spell) -> bool:
    """Return whether resource-level scaling gives the spell an upcast benefit.

    >>> from ..capabilities import (
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

    >>> spell = Spell(
    ...     "bless", "Bless", "XPHB", 1,
    ...     duration_data=({"duration": {"type": "minute", "amount": 1}},),
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
    for entry in spell.duration_data:
        duration = entry.get("duration")
        if not isinstance(duration, dict):
            continue
        unit = duration.get("type")
        amount = duration.get("amount")
        if isinstance(unit, str) and isinstance(amount, int):
            multiplier = rounds_per_unit.get(unit)
            if multiplier is not None:
                return amount * multiplier
    return None
