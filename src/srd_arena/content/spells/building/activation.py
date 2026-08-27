"""Translate authored casting time and duration into activation rules."""

from srd_arena.content.spells.schema import SpellSchema
from srd_arena.domain.capabilities import CapabilityActivation


def build_activation(raw: SpellSchema) -> CapabilityActivation | None:
    """Derive action economy, concentration, and duration from a spell record."""

    if not raw.time:
        return None
    activation_by_unit: dict[str, CapabilityActivation] = {
        "action": "action",
        "bonus": "bonus_action",
        "reaction": "reaction",
    }
    unit = raw.time[0].get("unit")
    if not isinstance(unit, str):
        return None
    return activation_by_unit.get(unit)
