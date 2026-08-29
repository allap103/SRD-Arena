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
from ...attack_economy import clear_attack_action, consume_action
from ...encounter_models.actions import (
    ActionCost,
    EncounterAction,
)

if TYPE_CHECKING:
    from ...encounter import EncounterState


def spell_action_cost(state: EncounterState, spell: Spell) -> ActionCost:
    """Map a spell's activation time to the turn resource it consumes.

    >>> from ....spells.metadata import SpellCastingTime
    >>> spell = Spell(
    ...     "healing_word", "Healing Word", "XPHB", 1,
    ...     casting_times=(SpellCastingTime(1, "bonus"),),
    ... )
    >>> spell_action_cost(None, spell).bonus_action
    1
    """

    economy = spell_action_economy(spell)
    return ActionCost(
        action=economy.action,
        bonus_action=economy.bonus_action,
        reaction=economy.reaction,
    )


def spell_cast_block_reason_for(
    state: EncounterState,
    spellcasting: Spellcasting,
    spell: Spell,
    cost: ActionCost,
    cast_level: int | None = None,
) -> str | None:
    """Return the rule reason that prevents this creature from casting a spell.

    >>> from types import SimpleNamespace
    >>> from ....creatures import Spellcasting
    >>> casting = Spellcasting(
    ...     "int", 3, 13, 5, "full", spell_slots_remaining={1: 0}
    ... )
    >>> spell = Spell("shield", "Shield", "XPHB", 1)
    >>> allowed = SimpleNamespace(allowed=True)
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="mage"),
    ...     combat_rules=SimpleNamespace(
    ...         action_compatibility=lambda *args: allowed,
    ...         reaction_eligibility=lambda *args: allowed,
    ...     ),
    ...     active_magic_actions_remaining=1,
    ...     active_bonus_action_available=True,
    ... )
    >>> spell_cast_block_reason_for(
    ...     state, casting, spell, ActionCost(action=1)
    ... )
    'You have no level 1 spell slots remaining.'
    """

    creature_ref = state.current_decision().creature_ref
    compatibility = state.combat_rules.action_compatibility(
        state,
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
        action_available=state.active_magic_actions_remaining > 0,
        bonus_action_available=state.active_bonus_action_available,
        reaction_available=state.combat_rules.reaction_eligibility(
            state,
            creature_ref,
            "spell",
        ).allowed,
        cast_level=cast_level,
    )


def spell_targets_self_only_for(state: EncounterState, spell: Spell) -> bool:
    """Return whether the spell's target contract permits only its caster.

    >>> spell = Spell("shield", "Shield", "XPHB", 1, geometry_mode="self_only")
    >>> spell_targets_self_only_for(None, spell)
    True
    """

    return spell.geometry_mode == "self_only" or spell_targets_self_only(spell)


def spell_range_squares_for(
    state: EncounterState, spell: Spell, creature: Creature
) -> int | None:
    """Convert the spell's authored range into grid cells for this caster.

    >>> from types import SimpleNamespace
    >>> from ....geometry import Grid
    >>> from ....spells.metadata import SpellRange, SpellRangeDistance
    >>> spell = Spell(
    ...     "bolt", "Bolt", "TEST", 0,
    ...     range=SpellRange("point", SpellRangeDistance("feet", 60)),
    ... )
    >>> state = SimpleNamespace(definition=SimpleNamespace(grid=Grid(10, 10)))
    >>> spell_range_squares_for(state, spell, None)
    12
    """

    return spell_range_squares(spell, state.definition.grid)


def spend_spell_resources(
    state: EncounterState,
    spellcasting: Spellcasting,
    spell: Spell,
    cost: ActionCost,
    cast_level: int | None = None,
) -> None:
    """Commit turn economy and spell-slot cost for an accepted casting.

    >>> from types import SimpleNamespace
    >>> from ....creatures import Spellcasting
    >>> casting = Spellcasting(
    ...     "int", 3, 13, 5, "full", spell_slots_remaining={1: 2}
    ... )
    >>> spell = Spell("magic_missile", "Magic Missile", "XPHB", 1)
    >>> actor = SimpleNamespace(
    ...     attacks_remaining=1, attack_action_base_attacks=1,
    ...     attack_action_attacks_used=0, pending_multiattack=[],
    ... )
    >>> state = SimpleNamespace(
    ...     active_actions_remaining=1, active_magic_actions_remaining=1,
    ...     active_creature_state=actor,
    ...     active_bonus_action_available=True, active_reaction_available=True,
    ... )
    >>> spend_spell_resources(state, casting, spell, ActionCost(action=1))
    >>> (casting.spell_slots_remaining[1], actor.attacks_remaining)
    (1, 0)
    """

    if cost.action > 0:
        consume_action(state, allow_magic=True)
        clear_attack_action(state.active_creature_state)
    if cost.bonus_action > 0:
        state.active_bonus_action_available = False
    if cost.reaction > 0:
        state.active_reaction_available = False
    if spell.level > 0:
        slot_level = cast_level if cast_level is not None else spell.level
        spellcasting.spell_slots_remaining[slot_level] -= 1
