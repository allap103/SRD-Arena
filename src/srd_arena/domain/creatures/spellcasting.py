from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..spells.definitions import Spell


@dataclass
class Spellcasting:
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
