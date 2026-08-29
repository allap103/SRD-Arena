"""Resolution for automatic-damage stat-block actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.capabilities import DamageEffect
from srd_arena.domain.creatures import Creature
from srd_arena.domain.creatures.stat_block_actions import AutomaticActionDefinition
from srd_arena.domain.rolls.dice import resolve_dice

from ...attack_economy import consume_action
from ...encounter_models.actions import EncounterAction
from ...encounter_models.resolution import EncounterProgress
from ...grappling_state import remove_relationships_for_creature
from ...rule_queries.defenses import apply_damage
from ...rule_queries.rolls import roll_modifiers
from ...state_runtime import create_event
from .resources import consume_stat_block_action_resource

if TYPE_CHECKING:
    from ...encounter import EncounterState


def resolve_automatic_stat_block_action(
    state: EncounterState,
    creature: Creature,
    definition: AutomaticActionDefinition,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Apply a supported automatic stat-block action to one target.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.capabilities import CapabilityTarget
    >>> definition = AutomaticActionDefinition(
    ...     "Aura", CapabilityTarget("creature"), ()
    ... )
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="monster")
    ... )
    >>> resolve_automatic_stat_block_action(
    ...     state, SimpleNamespace(), definition,
    ...     EncounterAction("Aura", "stat_block"), EncounterProgress(), "aura-1"
    ... )
    Traceback (most recent call last):
    ...
    ValueError: Automatic stat-block action requires a target.
    """
    creature_ref = state.current_decision().creature_ref
    if not isinstance(action.value, str):
        raise ValueError("Automatic stat-block action requires a target.")
    target_ref = action.value
    target = state.creatures[target_ref].creature
    consume_action(state, allow_magic=False)
    consume_stat_block_action_resource(creature, definition.name)
    damage = 0
    damage_details: list[dict[str, object]] = []
    damage_roll_rules = roll_modifiers(
        state,
        creature_ref,
        "damage_roll",
    )
    roll_die = state.dice.roll_die
    for effect in definition.effects:
        if not isinstance(effect, DamageEffect):
            raise NotImplementedError(
                f"Automatic effect '{type(effect).__name__}' is not executable."
            )
        count_text, sides_text = effect.dice.lower().split("d", 1)
        roll = resolve_dice(
            int(count_text),
            int(sides_text),
            modifier=effect.bonus,
            roller=roll_die,
        )
        sourced_modifier = damage_roll_rules.resolve_modifier(roll_die)
        resolved_total = roll.total + sourced_modifier
        amount = max(
            effect.minimum or 0,
            resolved_total,
        )
        applied = apply_damage(
            state,
            target_ref,
            amount,
            effect.damage_type,
        )
        damage += applied
        damage_details.append(
            {
                "damage_type": effect.damage_type,
                "dice": effect.dice,
                "dice_values": [die.result for die in roll.dice],
                "die_rolls": [list(die.rolls) for die in roll.dice],
                "dice_total": roll.subtotal,
                "modifier": roll.modifier + sourced_modifier,
                "sourced_modifier": sourced_modifier,
                "total": resolved_total,
                "minimum_applied_total": amount,
                "applied_damage": applied,
            }
        )
    progress.messages.append(
        (
            "system",
            f"{creature.name} uses {definition.name} on {target.name}, "
            f"dealing {damage} damage.",
        )
    )
    progress.events.append(
        create_event(
            state,
            "stat_block_action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "action_name": definition.name,
                "target_ref": target_ref,
                "damage": damage,
                "damage_details": damage_details,
            },
        )
    )
    if target.get_health() <= 0:
        remove_relationships_for_creature(state, target_ref)
        progress.events.append(
            create_event(
                state,
                "creature_defeated",
                creature_ref=target_ref,
                action_id=action_id,
            )
        )
