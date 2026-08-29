"""Translate authored casting time and duration into activation rules."""

from srd_arena.content.spells.schema import SpellSchema
from srd_arena.domain.capabilities import CapabilityActivation


def build_activation(raw: SpellSchema) -> CapabilityActivation | None:
    """Derive action economy from a spell's first casting-time entry.

    >>> spell = SpellSchema.model_validate({
    ...     "name": "Example", "source": "TEST", "level": 1, "school": "V",
    ...     "time": [{"number": 1, "unit": "bonus"}],
    ... })
    >>> build_activation(spell)
    'bonus_action'
    >>> build_activation(SpellSchema.model_construct(time=[])) is None
    True
    """

    if not raw.time:
        return None
    activation_by_unit: dict[str, CapabilityActivation] = {
        "action": "action",
        "bonus": "bonus_action",
        "reaction": "reaction",
    }
    unit = raw.time[0].unit
    return activation_by_unit.get(unit)
