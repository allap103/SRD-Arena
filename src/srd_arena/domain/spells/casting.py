"""Derive action-economy costs and immediate blockers for spell casting."""

from dataclasses import dataclass

from ..creatures import Spellcasting
from .definitions import Spell


@dataclass(frozen=True)
class SpellActionEconomy:
    """Count the turn resources consumed when a spell invocation starts."""

    action: int = 0
    bonus_action: int = 0
    reaction: int = 0


def spell_action_economy(spell: Spell) -> SpellActionEconomy:
    """Translate authored casting-time units into turn-resource costs.

    >>> from .metadata import SpellCastingTime
    >>> spell = Spell(
    ...     "healing_word", "Healing Word", "XPHB", 1,
    ...     casting_times=(SpellCastingTime(1, "bonus"),),
    ... )
    >>> spell_action_economy(spell)
    SpellActionEconomy(action=0, bonus_action=1, reaction=0)
    """

    units = {entry.unit for entry in spell.casting_times}
    return SpellActionEconomy(
        action=1 if "action" in units else 0,
        bonus_action=1 if "bonus" in units else 0,
        reaction=1 if "reaction" in units else 0,
    )


def spell_cast_block_reason(
    spellcasting: Spellcasting,
    spell: Spell,
    economy: SpellActionEconomy,
    *,
    action_available: bool,
    bonus_action_available: bool,
    reaction_available: bool,
    cast_level: int | None = None,
) -> str | None:
    """Return the first missing turn resource or spell slot preventing a cast.

    >>> casting = Spellcasting(
    ...     "wis", 3, 13, 5, "full", spell_slots_remaining={1: 0}
    ... )
    >>> spell = Spell("cure_wounds", "Cure Wounds", "XPHB", 1)
    >>> spell_cast_block_reason(
    ...     casting, spell, SpellActionEconomy(action=1),
    ...     action_available=True, bonus_action_available=True,
    ...     reaction_available=True,
    ... )
    'You have no level 1 spell slots remaining.'
    """

    if economy.action > 0 and not action_available:
        return "You have already used your Action."
    if economy.bonus_action > 0 and not bonus_action_available:
        return "You have already used your Bonus Action."
    if economy.reaction > 0 and not reaction_available:
        return "You have already used your Reaction."
    slot_level = cast_level if cast_level is not None else spell.level
    if spell.level > 0 and spellcasting.spell_slots_remaining.get(slot_level, 0) <= 0:
        return f"You have no level {slot_level} spell slots remaining."
    return None
