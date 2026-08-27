"""Provide spellcasting support for the creatures package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..capabilities import CapabilityGrant, SpellSlotCost, SpellSlotPool

if TYPE_CHECKING:
    from ..spells.definitions import Spell


@dataclass
class Spellcasting:
    """Represent a spellcasting."""

    ability: str
    ability_modifier: int
    save_dc: int
    attack_bonus: int
    caster_progression: str
    preparation_mode: str = "fixed"
    cantrips_known: int = 0
    spell_count: int | None = None
    spell_slots_max: dict[int, int] = field(default_factory=dict)
    spell_slots_remaining: dict[int, int] = field(default_factory=dict)
    learned_spells: list[Spell] = field(default_factory=list)

    @property
    def spell_slot_pool(self) -> SpellSlotPool:
        return SpellSlotPool(
            id="spell_slots",
            maximum_by_level=tuple(sorted(self.spell_slots_max.items())),
        )

    def grant_for(self, spell: Spell) -> CapabilityGrant | None:
        if spell.definition is None or spell.activation is None:
            return None
        cost = (
            SpellSlotCost(self.spell_slot_pool.id, spell.level)
            if spell.level > 0
            else None
        )
        return CapabilityGrant(
            id=spell.id,
            definition=spell.definition,
            activation=spell.activation,
            cost=cost,
        )
