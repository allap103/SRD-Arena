"""Expose and resolve attacks against destructible condition attachments."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from srd_arena.domain.effects.conditions import (
    AppliedCondition,
    DestructibleConditionState,
)
from srd_arena.domain.rolls.dice import combine_roll_modes
from srd_arena.domain.rolls.occurrences import attack_roll_occurrence_id

from ..attack_economy import record_attack_rolls, spend_attack, spend_current_attack
from ..attack_rules import proximity_attack_roll_mode
from ..condition_state import remove_condition_application
from ..encounter_models.actions import ActionCost, EncounterAction
from ..encounter_models.resolution import EncounterProgress
from ..participants import creatures_are_opponents
from ..rule_queries.obstructions import cover_between
from ..rule_queries.rolls import roll_modifiers
from ..rule_queries.visibility import creature_can_see_creature
from ..spatial import creature_distance
from ..state_runtime import create_event, creature_label
from .attack_resolution import (
    attack_range_band_squares,
    attack_sources,
    resolve_attack,
    selected_attack_ability,
    selected_attack_type,
)
from .d20_roll_modifiers import clear_d20_roll_modes, consume_d20_roll_mode
from .stat_block_runtime.resources import consume_stat_block_action_resource

if TYPE_CHECKING:
    from ..encounter import EncounterState


def destructible_condition_attack_actions(
    state: EncounterState,
    creature_ref: str,
) -> list[EncounterAction]:
    """Build attacks against active condition attachments such as webs."""

    actor = state.creatures[creature_ref]
    sources = attack_sources(actor.creature, state.item_templates)
    if actor.pending_multiattack:
        option_names = {
            invocation.name for invocation in actor.pending_multiattack[0].options
        }
        sources = [source for source in sources if source.name in option_names]
    actions: list[EncounterAction] = []
    for condition in state.conditions:
        attachment = condition.destructible
        target = state.creatures.get(condition.target_ref)
        if attachment is None or target is None or not target.is_alive:
            continue
        for source in sources:
            for attack_type in source.attack_modes:
                source_slug = _slug(source.name)
                condition_slug = _slug(condition.id)
                actions.append(
                    EncounterAction(
                        f"Attack {attachment.label} - {source.name}",
                        "attack_condition",
                        condition.target_ref,
                        id=(
                            f"{creature_ref}-attack-condition-{condition_slug}-"
                            f"{source_slug}-{attack_type}"
                        ),
                        creature_ref=creature_ref,
                        source_trigger_id=condition.id,
                        preferred_attack_type=attack_type,
                        preferred_attack_name=source.name,
                        cost=ActionCost(
                            action=1 if actor.attacks_remaining == 0 else 0
                        ),
                    )
                )
    return actions


def destructible_condition_for_action(
    state: EncounterState,
    action: EncounterAction,
) -> AppliedCondition | None:
    """Return the exact active attachment selected by an action."""

    if (
        action.kind != "attack_condition"
        or not isinstance(action.value, str)
        or action.source_trigger_id is None
    ):
        return None
    return next(
        (
            condition
            for condition in state.conditions
            if condition.id == action.source_trigger_id
            and condition.target_ref == action.value
            and condition.destructible is not None
        ),
        None,
    )


def resolve_destructible_condition_attack(
    state: EncounterState,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Resolve one ordinary attack roll against an attached condition."""

    condition = destructible_condition_for_action(state, action)
    if condition is None or condition.destructible is None:
        raise ValueError("The selected destructible condition is no longer active.")
    actor_ref = state.current_decision().creature_ref
    actor_state = state.creatures[actor_ref]
    attacker = actor_state.creature
    target_ref = condition.target_ref
    target = state.creatures[target_ref].creature
    preferred_name = action.preferred_attack_name
    if actor_state.pending_multiattack:
        slot = actor_state.pending_multiattack[0]
        if preferred_name not in {invocation.name for invocation in slot.options}:
            raise ValueError(
                "The selected attack is not available for this Multiattack slot."
            )
        spend_current_attack(state, actor_ref)
        actor_state.pending_multiattack.pop(0)
    else:
        spend_attack(
            state,
            actor_ref,
            base_attacks=attacker.combat_profile.attacks_per_attack_action,
        )

    attack_type = selected_attack_type(
        attacker,
        state.item_templates,
        preferred_attack_type=action.preferred_attack_type,
        preferred_attack_name=preferred_name,
    )
    attack_ability = selected_attack_ability(
        attacker,
        state.item_templates,
        preferred_attack_type=action.preferred_attack_type,
        preferred_attack_name=preferred_name,
    )
    nearby_opponent_refs = tuple(
        opponent_ref
        for opponent_ref, candidate in state.creatures.items()
        if candidate.is_alive
        and creatures_are_opponents(state, actor_ref, opponent_ref)
    )
    nearby_opponent_positions = tuple(
        state.creatures[opponent_ref].position for opponent_ref in nearby_opponent_refs
    )
    range_band = attack_range_band_squares(
        attacker,
        state.item_templates,
        state.definition.grid,
        preferred_attack_type=action.preferred_attack_type,
        preferred_attack_name=preferred_name,
    )
    range_mode = range_band.roll_mode(creature_distance(state, actor_ref, target_ref))
    attack_rules = roll_modifiers(
        state,
        actor_ref,
        "attack_roll",
        attack_ability,
    )
    cover = cover_between(state, actor_ref, target_ref)
    attachment = condition.destructible
    target_label = f"{attachment.label} on {creature_label(state, target_ref)}"
    roll_die = state.dice.roll_die
    record_attack_rolls(state, actor_ref)
    outcome = resolve_attack(
        attacker,
        target,
        attacker_label=attacker.name,
        target_label=target_label,
        items_by_id=state.item_templates,
        attacker_position=actor_state.position,
        nearby_opponent_positions=nearby_opponent_positions,
        preferred_attack_name=preferred_name,
        preferred_attack_type=action.preferred_attack_type,
        attack_roll_mode_override=combine_roll_modes(
            proximity_attack_roll_mode(
                attack_type,
                actor_state.position,
                nearby_opponent_positions,
            ),
            (
                "normal"
                if creature_can_see_creature(state, actor_ref, target_ref)
                else "disadvantage"
            ),
            attack_rules.mode,
            range_mode,
            consume_d20_roll_mode(
                state,
                action_id,
                attack_roll_occurrence_id(),
            ),
        ),
        sourced_attack_modifier=attack_rules.resolve_modifier(roll_die),
        target_armor_class=attachment.armor_class + cover.bonus,
        sourced_damage_modifier_for=lambda ability: roll_modifiers(
            state,
            actor_ref,
            "damage_roll",
            ability,
        ).resolve_modifier(roll_die),
        d20_roller=roll_die,
        die_roller=roll_die,
    )
    clear_d20_roll_modes(state, action_id)
    if isinstance(preferred_name, str):
        consume_stat_block_action_resource(attacker, preferred_name)

    progress.messages.extend(outcome.messages)
    applied_damage = 0
    destroyed = False
    remaining_hit_points = attachment.hit_points
    if outcome.hit and outcome.damage_roll is not None:
        applied_damage += _attachment_damage(
            attachment,
            max(1, outcome.damage_roll.total),
            outcome.damage_type,
        )
        for detail in outcome.additional_damage_details:
            amount = detail.get("total")
            damage_type = detail.get("damage_type")
            if isinstance(amount, int):
                applied_damage += _attachment_damage(
                    attachment,
                    amount,
                    damage_type if isinstance(damage_type, str) else None,
                )
        remaining_hit_points = max(0, attachment.hit_points - applied_damage)
        destroyed = remaining_hit_points == 0
        outcome.damage = applied_damage
        if outcome.damage_roll_detail is not None:
            outcome.damage_roll_detail["applied_damage"] = applied_damage
            outcome.damage_roll_detail["remaining_attachment_hit_points"] = (
                remaining_hit_points
            )
        if destroyed:
            remove_condition_application(state, condition.id)
            progress.messages.append(
                ("system", f"{attacker.name} destroys {target_label}.")
            )
        else:
            _replace_attachment_hit_points(
                state,
                condition,
                remaining_hit_points,
            )
            progress.messages.append(
                (
                    "system",
                    f"{attacker.name} damages {target_label} for {applied_damage}; "
                    f"{remaining_hit_points} HP remain.",
                )
            )
    progress.events.append(
        create_event(
            state,
            "destructible_condition_attacked",
            creature_ref=actor_ref,
            action_id=action_id,
            data={
                "condition_id": condition.id,
                "condition": condition.condition.value,
                "target_ref": target_ref,
                "attachment_label": attachment.label,
                "attack_name": preferred_name,
                "attack_type": attack_type,
                "attack_roll": outcome.attack_roll,
                "attack_roll_detail": outcome.attack_roll_detail,
                "hit": outcome.hit,
                "critical_hit": outcome.critical_hit,
                "damage": applied_damage,
                "damage_roll_detail": outcome.damage_roll_detail,
                "remaining_hit_points": remaining_hit_points,
                "destroyed": destroyed,
            },
        )
    )


def _attachment_damage(
    attachment: DestructibleConditionState,
    amount: int,
    damage_type: str | None,
) -> int:
    normalized = damage_type.casefold() if damage_type is not None else None
    if normalized in attachment.damage_immunities:
        return 0
    if normalized in attachment.damage_vulnerabilities:
        return amount * 2
    return amount


def _replace_attachment_hit_points(
    state: EncounterState,
    condition: AppliedCondition,
    hit_points: int,
) -> None:
    assert condition.destructible is not None
    replacement = replace(
        condition,
        destructible=replace(condition.destructible, hit_points=hit_points),
    )
    state.conditions = [
        replacement if existing.id == condition.id else existing
        for existing in state.conditions
    ]


def _slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value)
