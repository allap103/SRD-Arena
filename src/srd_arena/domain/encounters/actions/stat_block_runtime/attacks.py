"""Attack resolution for creature and authored stat-block attacks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from srd_arena.domain.creatures import Creature
from srd_arena.domain.rolls.dice import combine_roll_modes
from srd_arena.domain.rolls.occurrences import attack_roll_occurrence_id

from ...attack_economy import record_attack_rolls, spend_attack, spend_current_attack
from ...defeat import resolve_creature_defeat
from ...encounter_models.actions import EncounterAction
from ...encounter_models.resolution import EncounterProgress
from ...participants import creatures_are_opponents
from ...reaction_runtime.attack_lifecycle import resolve_attack_lifecycle
from ...reaction_runtime.damage_rerolls import open_damage_reroll_decision
from ...rule_queries.damage_riders import attack_hit_damage
from ...rule_queries.numeric import effective_armor_class
from ...rule_queries.obstructions import cover_between
from ...rule_queries.retaliation import attack_hit_retaliations
from ...rule_queries.rolls import roll_modifiers
from ...spatial import creature_distance
from ...state_combat import (
    apply_combat_damage,
    attack_roll_mode_for,
    automatic_critical_provider_ids_for,
)
from ...state_runtime import create_event, creature_label
from ..attack_resolution import (
    apply_attack_damage,
    attack_range_band_squares,
    matching_damage_reroll_rule,
    resolve_attack,
    selected_attack_ability,
    selected_attack_type,
)
from ..d20_roll_modifiers import (
    clear_d20_roll_modes,
    consume_d20_roll_mode,
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
    nearby_opponent_refs = tuple(
        opponent_ref
        for opponent_ref, candidate in state.creatures.items()
        if candidate.is_alive
        and creatures_are_opponents(state, creature_ref, opponent_ref)
    )
    nearby_opponent_positions = tuple(
        state.creatures[opponent_ref].position for opponent_ref in nearby_opponent_refs
    )
    attack_ability = selected_attack_ability(
        creature,
        state.item_templates,
        preferred_attack_type=action.preferred_attack_type,
        preferred_attack_name=preferred_attack_name,
    )
    attack_roll_rules = roll_modifiers(
        state,
        creature_ref,
        "attack_roll",
        attack_ability,
    )
    attack_type = selected_attack_type(
        creature,
        state.item_templates,
        preferred_attack_type=action.preferred_attack_type,
        preferred_attack_name=preferred_attack_name,
    )
    range_band = attack_range_band_squares(
        creature,
        state.item_templates,
        state.definition.grid,
        preferred_attack_type=action.preferred_attack_type,
        preferred_attack_name=preferred_attack_name,
    )
    range_roll_mode = range_band.roll_mode(
        creature_distance(state, creature_ref, target_ref)
    )
    cover = cover_between(state, creature_ref, target_ref)
    roll_die = state.dice.roll_die
    record_attack_rolls(state, creature_ref)
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
        attack_roll_mode_override=combine_roll_modes(
            attack_roll_mode_for(
                state,
                creature_ref,
                target_ref,
                attack_type,
                creature_state.position,
                nearby_opponent_positions,
                nearby_opponent_refs=nearby_opponent_refs,
                attack_ability=attack_ability,
            ),
            range_roll_mode,
            consume_d20_roll_mode(
                state,
                action_id,
                attack_roll_occurrence_id(),
            ),
        ),
        sourced_attack_modifier=attack_roll_rules.resolve_modifier(roll_die),
        target_armor_class=effective_armor_class(
            state,
            target_ref,
        ).value
        + cover.bonus,
        sourced_damage_modifier_for=lambda ability: roll_modifiers(
            state,
            creature_ref,
            "damage_roll",
            ability,
        ).resolve_modifier(roll_die),
        d20_roller=roll_die,
        die_roller=roll_die,
        automatic_critical_provider_ids=(
            automatic_critical_provider_ids_for(
                state,
                creature_ref,
                target_ref,
            )
        ),
        sourced_additional_damage=tuple(
            (contribution.provider_state_id, contribution.value)
            for contribution in attack_hit_damage(state, creature_ref, target_ref)
        ),
    )
    clear_d20_roll_modes(state, action_id)
    if isinstance(preferred_attack_name, str):
        consume_stat_block_action_resource(creature, preferred_attack_name)
    retaliations = (
        attack_hit_retaliations(state, target_ref, attack_type) if outcome.hit else ()
    )
    outcome.attack_roll_detail["cover_degree"] = cover.degree.value
    outcome.attack_roll_detail["cover_bonus"] = cover.bonus
    reroll_rule = matching_damage_reroll_rule(
        creature,
        outcome,
        excluded_effect_ids=creature_state.features_used_this_turn,
        allowed_operations=("roll_damage_pool_twice",),
    )
    if outcome.hit and reroll_rule is not None:
        open_damage_reroll_decision(
            state,
            attack=outcome,
            triggered_effect=reroll_rule,
            attacker_ref=creature_ref,
            target_ref=target_ref,
            attacker_label=creature.name,
            target_label=target_label,
            action_id=action_id,
            progress=progress,
        )
        return
    apply_attack_damage(
        outcome,
        defender,
        attacker_label=creature.name,
        target_label=target_label,
        damage_receiver=lambda amount, damage_type: apply_combat_damage(
            state,
            target_ref,
            amount,
            damage_type,
        ),
    )
    resolve_attack_lifecycle(
        state,
        attacker_ref=creature_ref,
        target_ref=target_ref,
        damage=outcome.damage,
        progress=progress,
        retaliations=retaliations,
        action_id=action_id,
    )
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
    if outcome.defender_defeated:
        resolve_creature_defeat(
            state,
            target_ref,
            defeated_by_ref=creature_ref,
            progress=progress,
            action_id=action_id,
        )
