"""Finalize an attack after optional post-hit decisions have resolved."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..defeat import resolve_creature_defeat
from ..encounter_models.decisions import DecisionContinuation
from ..encounter_models.resolution import AttackOutcome, EncounterProgress
from ..reaction_runtime.attack_lifecycle import resolve_attack_lifecycle
from ..reaction_runtime.damage_rerolls import open_damage_reroll_decision
from ..rule_queries.retaliation import attack_hit_retaliations
from ..state_combat import apply_combat_damage
from ..state_runtime import create_event
from .attack_resolution import (
    apply_attack_damage,
    matching_damage_reroll_rule,
)
from .hit_effects import apply_attack_hit_effects
from .weapon_mastery import (
    mastery_request_for_attack,
    open_weapon_mastery_decision,
)

if TYPE_CHECKING:
    from ..encounter import EncounterState


def continue_pending_attack(
    state: EncounterState,
    *,
    attack: AttackOutcome,
    attacker_ref: str,
    target_ref: str,
    attacker_label: str,
    target_label: str,
    attack_name: str | None,
    attacks_remaining: int,
    action_id: str,
    progress: EncounterProgress,
    on_hit_feature_ids: tuple[str, ...] = (),
    frame_id: str | None = None,
    continuation: DecisionContinuation | None = None,
    reaction: bool = False,
) -> bool:
    """Apply or further suspend one attack after defensive reactions."""

    attacker_state = state.creatures[attacker_ref]
    if attack.hit:
        attacker_state.features_used_this_turn.update(on_hit_feature_ids)
    reroll_rule = matching_damage_reroll_rule(
        attacker_state.creature,
        attack,
        excluded_effect_ids=attacker_state.features_used_this_turn,
        allowed_operations=("roll_damage_pool_twice",),
    )
    if attack.hit and reroll_rule is not None:
        open_damage_reroll_decision(
            state,
            attack=attack,
            triggered_effect=reroll_rule,
            attacker_ref=attacker_ref,
            target_ref=target_ref,
            attacker_label=attacker_label,
            target_label=target_label,
            action_id=action_id,
            progress=progress,
            continuation=continuation,
            reaction=reaction,
        )
        return True

    target = state.creatures[target_ref]
    retaliations = (
        attack_hit_retaliations(state, target_ref, attack.attack_type)
        if attack.hit
        else ()
    )
    apply_attack_damage(
        attack,
        target.creature,
        attacker_label=attacker_label,
        target_label=target_label,
        damage_receiver=lambda amount, damage_type: apply_combat_damage(
            state,
            target_ref,
            amount,
            damage_type,
            critical_hit=attack.critical_hit,
        ),
    )
    resolve_attack_lifecycle(
        state,
        attacker_ref=attacker_ref,
        target_ref=target_ref,
        damage=attack.damage,
        progress=progress,
        retaliations=retaliations,
        action_id=action_id,
        frame_id=frame_id,
    )
    if attack.hit and target.is_alive:
        apply_attack_hit_effects(
            state,
            attacker_ref=attacker_ref,
            target_ref=target_ref,
            effects=attack.hit_effects,
            progress=progress,
            origin_id=action_id,
        )
    progress.messages.extend(attack.messages)
    progress.events.append(
        create_event(
            state,
            "attack_resolved",
            creature_ref=attacker_ref,
            frame_id=frame_id,
            action_id=action_id,
            data={
                "attacker_label": attacker_label,
                "target_ref": target_ref,
                "target_label": target_label,
                "attack_name": attack_name,
                "attack_roll": attack.attack_roll,
                "attack_roll_detail": attack.attack_roll_detail,
                "hit": attack.hit,
                "critical_hit": attack.critical_hit,
                "damage": attack.damage,
                "damage_roll_detail": attack.damage_roll_detail,
                "attacks_remaining": attacks_remaining,
                "reaction": reaction,
            },
        )
    )
    if attack.defender_defeated:
        resolve_creature_defeat(
            state,
            target_ref,
            defeated_by_ref=attacker_ref,
            progress=progress,
            frame_id=frame_id,
            action_id=action_id,
        )
    mastery_request = mastery_request_for_attack(
        state,
        attack,
        attacker_ref=attacker_ref,
        target_ref=target_ref,
        action_id=action_id,
    )
    if mastery_request is not None:
        open_weapon_mastery_decision(
            state,
            mastery_request,
            progress,
            continuation=continuation,
        )
        return True
    return False
