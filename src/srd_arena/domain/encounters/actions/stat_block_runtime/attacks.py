"""Attack resolution for creature and authored stat-block attacks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....creatures import Creature
from ...attack_economy import spend_attack, spend_current_attack
from ...effect_lifecycle.concentration import resolve_concentration_damage
from ...effect_lifecycle.lifecycle_events import resolve_spell_lifecycle_event
from ...encounter_models.actions import EncounterAction
from ...encounter_models.resolution import EncounterProgress
from ...grappling_state import remove_relationships_for_creature
from ...participants import creatures_are_opponents
from ...state_combat import attack_roll_mode_for, automatic_critical_provider_ids_for
from ...state_runtime import create_event, creature_label
from ..attack_resolution import (
    apply_attack_damage,
    resolve_attack,
    selected_attack_type,
)
from ..hit_effects import apply_attack_hit_effects
from .resources import consume_stat_block_action_resource

if TYPE_CHECKING:
    from ...encounter import EncounterState


def resolve_attack_action(
    state: EncounterState,
    creature: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Resolve one attack, including multiattack state and hit effects.

    A pending Multiattack slot rejects attacks outside its authored options.

    >>> from types import SimpleNamespace
    >>> slot = SimpleNamespace(options=(SimpleNamespace(name="Bite"),))
    >>> creature_state = SimpleNamespace(pending_multiattack=[slot])
    >>> state = SimpleNamespace(
    ...     current_decision=lambda: SimpleNamespace(creature_ref="dragon"),
    ...     creatures={"dragon": creature_state},
    ... )
    >>> resolve_attack_action(
    ...     state, SimpleNamespace(),
    ...     EncounterAction("Claw", "attack", preferred_attack_name="Claw"),
    ...     EncounterProgress(), "attack-1"
    ... )
    Traceback (most recent call last):
    ...
    ValueError: The selected attack is not available for this Multiattack slot.
    """
    creature_ref = state.current_decision().creature_ref
    creature_state = state.creatures[creature_ref]
    preferred_attack_name = action.preferred_attack_name
    if creature_state.pending_multiattack:
        slot = creature_state.pending_multiattack[0]
        if preferred_attack_name not in {
            invocation.name for invocation in slot.options
        }:
            raise ValueError(
                "The selected attack is not available for this Multiattack slot."
            )
        spend_current_attack(state, creature_ref)
        creature_state.pending_multiattack.pop(0)
    else:
        spend_attack(
            state,
            creature_ref,
            base_attacks=creature.combat_profile.attacks_per_attack_action,
        )
    if not isinstance(action.value, str):
        raise ValueError("Attack action requires a creature reference.")
    target_ref = action.value
    if not creatures_are_opponents(state, creature_ref, target_ref):
        raise ValueError("Attack target must belong to an opposing team.")
    defender = state.creatures[target_ref].creature
    target_label = creature_label(state, target_ref)
    nearby_opponent_positions = tuple(
        candidate.position
        for opponent_ref, candidate in state.creatures.items()
        if candidate.is_alive
        and creatures_are_opponents(state, creature_ref, opponent_ref)
    )
    attack_roll_rules = state.combat_rules.roll_modifiers(
        state,
        creature_ref,
        "attack_roll",
    )
    damage_roll_rules = state.combat_rules.roll_modifiers(
        state,
        creature_ref,
        "damage_roll",
    )
    roll_die = state.dice.roll_die
    outcome = resolve_attack(
        creature,
        defender,
        attacker_label=creature.name,
        target_label=target_label,
        items_by_id=state.item_templates,
        attacker_position=creature_state.position,
        nearby_opponent_positions=nearby_opponent_positions,
        preferred_attack_name=preferred_attack_name,
        preferred_attack_type=action.preferred_attack_type,
        attack_roll_mode_override=attack_roll_mode_for(
            state,
            creature_ref,
            target_ref,
            selected_attack_type(
                creature,
                state.item_templates,
                preferred_attack_type=action.preferred_attack_type,
            ),
            creature_state.position,
            nearby_opponent_positions,
        ),
        sourced_attack_modifier=attack_roll_rules.resolve_modifier(roll_die),
        sourced_attack_roll_mode=attack_roll_rules.mode,
        target_armor_class=state.combat_rules.effective_armor_class(
            state,
            target_ref,
        ).value,
        sourced_damage_modifier_for=lambda: damage_roll_rules.resolve_modifier(
            roll_die
        ),
        d20_roller=roll_die,
        die_roller=roll_die,
        automatic_critical_provider_ids=(
            automatic_critical_provider_ids_for(
                state,
                creature_ref,
                target_ref,
            )
        ),
    )
    if isinstance(preferred_attack_name, str):
        consume_stat_block_action_resource(creature, preferred_attack_name)
    apply_attack_damage(
        outcome,
        defender,
        attacker_label=creature.name,
        target_label=target_label,
        damage_receiver=lambda amount, damage_type: state.combat_rules.apply_damage(
            state,
            target_ref,
            amount,
            damage_type,
        ),
    )
    resolve_spell_lifecycle_event(
        state,
        "target_makes_attack",
        actor_ref=creature_ref,
        target_ref=target_ref,
        progress=progress,
    )
    if outcome.damage > 0:
        resolve_spell_lifecycle_event(
            state,
            "target_damaged",
            actor_ref=creature_ref,
            target_ref=target_ref,
            progress=progress,
        )
        resolve_spell_lifecycle_event(
            state,
            "target_deals_damage",
            actor_ref=creature_ref,
            target_ref=target_ref,
            progress=progress,
        )
    resolve_concentration_damage(state, target_ref, outcome.damage, progress)
    if outcome.hit and defender.get_health() > 0:
        apply_attack_hit_effects(
            state,
            attacker_ref=creature_ref,
            target_ref=target_ref,
            effects=outcome.hit_effects,
            progress=progress,
            origin_id=action_id,
        )
    progress.messages.extend(outcome.messages)
    progress.events.append(
        create_event(
            state,
            "attack_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "attacker_label": creature.name,
                "target_ref": target_ref,
                "target_label": target_label,
                "attack_name": preferred_attack_name,
                "attack_roll": outcome.attack_roll,
                "attack_roll_detail": outcome.attack_roll_detail,
                "hit": outcome.hit,
                "critical_hit": outcome.critical_hit,
                "damage": outcome.damage,
                "damage_roll_detail": outcome.damage_roll_detail,
                "attacks_remaining": creature_state.attacks_remaining,
            },
        )
    )
    if defender.get_health() <= 0:
        remove_relationships_for_creature(state, target_ref)
        progress.events.append(
            create_event(
                state,
                "creature_defeated",
                creature_ref=target_ref,
                action_id=action_id,
            )
        )
