"""Track a creature's spellcasting statistics, known spells, and spell slots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from srd_arena.domain.capabilities import CapabilityGrant, SpellSlotCost, SpellSlotPool

from .resources import ResourceRecovery, RestType

if TYPE_CHECKING:
    from srd_arena.domain.spells.definitions import Spell


@dataclass
class Spellcasting:
    """Own creature-specific casting context and player-style spell-slot state.

    Spells retain universal metadata and mechanics; this component supplies the
    ability modifier, save DC, attack bonus, learned set, and resources used by
    this particular creature when it casts them.
    """

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
        """Project maximum slots as a capability resource pool.

        >>> casting = Spellcasting("int", 4, 15, 7, "full", spell_slots_max={1: 4, 2: 3})
        >>> casting.spell_slot_pool.maximum_by_level
        ((1, 4), (2, 3))
        """
        return SpellSlotPool(
            id="spell_slots",
            maximum_by_level=tuple(sorted(self.spell_slots_max.items())),
            refresh=(
                "short_rest" if self.caster_progression == "pact" else "long_rest"
            ),
        )

    def spend_slot(self, level: int) -> int:
        """Spend one slot of the requested level and return the new remainder.

        >>> casting = Spellcasting(
        ...     "cha", 3, 13, 5, "pact", spell_slots_remaining={2: 2}
        ... )
        >>> casting.spend_slot(2)
        1
        """

        remaining = self.spell_slots_remaining.get(level, 0)
        if remaining <= 0:
            raise RuntimeError(f"No level {level} spell slots remain.")
        self.spell_slots_remaining[level] = remaining - 1
        return self.spell_slots_remaining[level]

    def recover_slots(self, rest: RestType) -> tuple[ResourceRecovery, ...]:
        """Restore spell slots whose pool refreshes at the completed rest.

        Pact Magic refreshes on either rest. Other spellcasting represented by
        this component refreshes only on a Long Rest.

        >>> casting = Spellcasting(
        ...     "cha", 3, 13, 5, "pact",
        ...     spell_slots_max={2: 2}, spell_slots_remaining={2: 0},
        ... )
        >>> casting.recover_slots(RestType.SHORT)[0].current
        2
        """

        refresh = self.spell_slot_pool.refresh
        if rest is RestType.SHORT and refresh != "short_rest":
            return ()
        recoveries: list[ResourceRecovery] = []
        for level, maximum in sorted(self.spell_slots_max.items()):
            previous = self.spell_slots_remaining.get(level, maximum)
            if previous >= maximum:
                continue
            self.spell_slots_remaining[level] = maximum
            recoveries.append(
                ResourceRecovery(
                    resource_id=f"{self.spell_slot_pool.id}:{level}",
                    previous=previous,
                    current=maximum,
                )
            )
        return tuple(recoveries)

    def grant_for(self, spell: Spell) -> CapabilityGrant | None:
        """Create a castable grant when the spell has executable mechanics.

        >>> from srd_arena.domain.spells import Spell
        >>> casting = Spellcasting("int", 4, 15, 7, "full")
        >>> casting.grant_for(Spell("unknown", "Unknown", None, 1)) is None
        True
        """
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
