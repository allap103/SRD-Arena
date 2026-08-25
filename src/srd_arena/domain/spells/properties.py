from .definitions import Spell


def spell_supports_higher_level(spell: Spell) -> bool:
    if spell.definition is not None:
        return any(
            scaling.basis == "resource_level" and scaling.per_level
            for scaling in spell.definition.scaling
        )
    return False


def spell_duration_rounds(spell: Spell) -> int | None:
    """Return the spell metadata duration converted to encounter rounds."""
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
