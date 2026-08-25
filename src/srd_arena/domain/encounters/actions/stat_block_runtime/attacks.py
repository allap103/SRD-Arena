"""Attack resolution for creature and authored stat-block attacks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ....creatures import Creature
from ...attack_economy import spend_attack
from ..attack_resolution import (
    apply_attack_damage,
    resolve_attack,
    selected_attack_type,
)
from ..hit_effects import apply_attack_hit_effects
from .resources import consume_stat_block_action_resource
from .rolls import roll_dice, roll_die
from ...models import EncounterAction, EncounterProgress
from ...ongoing_effects import (
    resolve_concentration_damage,
    resolve_spell_lifecycle_event,
)

if TYPE_CHECKING:
    from ...encounter import EncounterState


def resolve_attack_action(
    state: EncounterState,
    creature: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Resolve one attack, including multiattack state and hit effects."""
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
        creature_state.pending_multiattack.pop(0)
        creature_state.attacks_remaining = len(creature_state.pending_multiattack)
    else:
        spend_attack(
            state,
            creature_ref,
            base_attacks=creature.combat_profile.attacks_per_attack_action,
        )
    if not isinstance(action.value, str):
        raise ValueError("Attack action requires a creature reference.")
    target_ref = action.value
    if not state._creatures_are_opponents(creature_ref, target_ref):
        raise ValueError("Attack target must belong to an opposing team.")
    defender = state.creatures[target_ref].creature
    target_label = state._creature_label(target_ref)
    nearby_opponent_positions = tuple(
        candidate.position
        for opponent_ref, candidate in state.creatures.items()
        if candidate.is_alive
        and state._creatures_are_opponents(creature_ref, opponent_ref)
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
        attack_roll_mode_override=state._attack_roll_mode_for(
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
        dice_roller=roll_dice,
        automatic_critical_provider_ids=(
            state._automatic_critical_provider_ids_for(
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
        state._event(
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
        state._remove_relationships_for_creature(target_ref)
        progress.events.append(
            state._event(
                "creature_defeated",
                creature_ref=target_ref,
                action_id=action_id,
            )
        )
