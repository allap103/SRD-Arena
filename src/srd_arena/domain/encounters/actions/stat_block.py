from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature
from ...creatures.stat_block_actions import AttackActionDefinition
from .attack_resolution import (
    apply_attack_damage,
    resolve_attack,
    selected_attack_type,
)
from .hit_effects import apply_attack_hit_effects
from ..models import EncounterAction, EncounterProgress

if TYPE_CHECKING:
    from ..encounter import EncounterState


def _roll_die(sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_die(sides)


def _roll_dice(count: int, sides: int) -> int:
    from .. import encounter as encounter_module

    return encounter_module.roll_dice(count, sides)


def executable_multiattack_sequence(creature: Creature):
    if creature.multiattack is None:
        return None
    return creature.multiattack.executable_sequence(
        {
            action.name
            for action in creature.stat_block_actions.values()
            if isinstance(action, AttackActionDefinition)
        }
    )


def resolve_multiattack_action(
    state: EncounterState,
    creature: Creature,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    creature_ref = state.current_decision().creature_ref
    creature_state = state.creatures[creature_ref]
    if creature_state.actions_remaining <= 0 or creature_state.attacks_remaining > 0:
        raise RuntimeError("No Action remains to make a Multiattack.")
    sequence = executable_multiattack_sequence(creature)
    if not sequence:
        raise RuntimeError("This creature has no executable Multiattack plan.")
    state._consume_action(allow_magic=False)
    creature_state.pending_multiattack = list(sequence)
    creature_state.attacks_remaining = len(sequence)
    progress.messages.append(
        ("system", f"{creature.name} begins Multiattack.")
    )
    progress.events.append(
        state._event(
            "action_resolved",
            creature_ref=creature_ref,
            action_id=action_id,
            data={
                "kind": "multiattack",
                "sequence": [invocation.name for invocation in sequence],
            },
        )
    )


def resolve_attack_action(
    state: EncounterState,
    creature: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    creature_ref = state.current_decision().creature_ref
    creature_state = state.creatures[creature_ref]
    preferred_attack_name = action.preferred_attack_name
    if creature_state.pending_multiattack:
        preferred_attack_name = creature_state.pending_multiattack.pop(0).name
        creature_state.attacks_remaining = len(
            creature_state.pending_multiattack
        )
    elif creature_state.attacks_remaining == 0:
        if creature_state.actions_remaining <= 0:
            raise RuntimeError("No Action remains to make an attack.")
        state._consume_action(allow_magic=False)
        creature_state.attacks_remaining = max(
            0,
            creature.combat_profile.attacks_per_attack_action - 1,
        )
    else:
        creature_state.attacks_remaining -= 1
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
        d20_roller=_roll_die,
        dice_roller=_roll_dice,
    )
    apply_attack_damage(
        outcome,
        defender,
        attacker_label=creature.name,
        target_label=target_label,
    )
    if outcome.hit and defender.get_health() > 0:
        apply_attack_hit_effects(
            state,
            attacker_ref=creature_ref,
            target_ref=target_ref,
            effects=outcome.hit_effects,
            progress=progress,
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
        state._remove_relational_statuses_for_creature(target_ref)
        progress.events.append(
            state._event(
                "creature_defeated",
                creature_ref=target_ref,
                action_id=action_id,
            )
        )
