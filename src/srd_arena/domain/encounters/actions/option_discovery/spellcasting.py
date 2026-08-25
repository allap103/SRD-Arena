from __future__ import annotations

from typing import TYPE_CHECKING

from ....creatures import Creature, Spellcasting
from ....spells.definitions import Spell
from ....spells.rules import (
    spell_action_economy,
    spell_cast_block_reason,
    spell_range_squares,
    spell_targets_self_only,
)
from ...models import ActionCost

if TYPE_CHECKING:
    from ...encounter import EncounterState


def spell_action_cost(self: EncounterState, spell: Spell) -> ActionCost:
    economy = spell_action_economy(spell)
    return ActionCost(
        action=economy.action,
        bonus_action=economy.bonus_action,
        reaction=economy.reaction,
    )


def spell_cast_block_reason_for(
    self: EncounterState,
    spellcasting: Spellcasting,
    spell: Spell,
    cost: ActionCost,
    cast_level: int | None = None,
) -> str | None:
    return spell_cast_block_reason(
        spellcasting,
        spell,
        spell_action_economy(spell),
        action_available=self.active_magic_actions_remaining > 0,
        bonus_action_available=self.active_bonus_action_available,
        reaction_available=self.active_reaction_available,
        cast_level=cast_level,
    )


def spell_targets_self_only_for(self: EncounterState, spell: Spell) -> bool:
    return spell.geometry_mode == "self_only" or spell_targets_self_only(spell)


def spell_range_squares_for(
    self: EncounterState, spell: Spell, creature: Creature
) -> int | None:
    return spell_range_squares(spell, self.definition.grid)


def spend_spell_resources(
    self: EncounterState,
    spellcasting: Spellcasting,
    spell: Spell,
    cost: ActionCost,
    cast_level: int | None = None,
) -> None:
    if cost.action > 0:
        self._consume_action(allow_magic=True)
        self.active_attacks_remaining = 0
    if cost.bonus_action > 0:
        self.active_bonus_action_available = False
    if cost.reaction > 0:
        self.active_reaction_available = False
    if spell.level > 0:
        slot_level = cast_level if cast_level is not None else spell.level
        spellcasting.spell_slots_remaining[slot_level] -= 1
