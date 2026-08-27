"""Derive casting costs and eligibility facts for a creature's spell grants."""

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
from ...attack_economy import clear_attack_action
from ...models import ActionCost, EncounterAction

if TYPE_CHECKING:
    from ...encounter import EncounterState


def spell_action_cost(self: EncounterState, spell: Spell) -> ActionCost:
    """Map a spell's activation time to the turn resource it consumes."""

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
    """Return the rule reason that prevents this creature from casting a spell."""

    creature_ref = self.current_decision().creature_ref
    compatibility = self.combat_rules.action_compatibility(
        self,
        creature_ref,
        EncounterAction(
            spell.name,
            "spell",
            creature_ref=creature_ref,
            cost=cost,
        ),
    )
    if not compatibility.allowed:
        return compatibility.failures[0].message
    return spell_cast_block_reason(
        spellcasting,
        spell,
        spell_action_economy(spell),
        action_available=self.active_magic_actions_remaining > 0,
        bonus_action_available=self.active_bonus_action_available,
        reaction_available=self.combat_rules.reaction_eligibility(
            self,
            creature_ref,
            "spell",
        ).allowed,
        cast_level=cast_level,
    )


def spell_targets_self_only_for(self: EncounterState, spell: Spell) -> bool:
    """Return whether the spell's target contract permits only its caster."""

    return spell.geometry_mode == "self_only" or spell_targets_self_only(spell)


def spell_range_squares_for(
    self: EncounterState, spell: Spell, creature: Creature
) -> int | None:
    """Convert the spell's authored range into grid cells for this caster."""

    return spell_range_squares(spell, self.definition.grid)


def spend_spell_resources(
    self: EncounterState,
    spellcasting: Spellcasting,
    spell: Spell,
    cost: ActionCost,
    cast_level: int | None = None,
) -> None:
    """Commit the grant-specific daily use or slot cost for an accepted casting."""

    if cost.action > 0:
        self._consume_action(allow_magic=True)
        clear_attack_action(self.active_creature_state)
    if cost.bonus_action > 0:
        self.active_bonus_action_available = False
    if cost.reaction > 0:
        self.active_reaction_available = False
    if spell.level > 0:
        slot_level = cast_level if cast_level is not None else spell.level
        spellcasting.spell_slots_remaining[slot_level] -= 1
