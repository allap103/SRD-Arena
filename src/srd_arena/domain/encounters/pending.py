from __future__ import annotations

from ..rolls.dice import DicePoolResult, DieReplacement, DieRollResult
from ..effects.triggered import TriggeredEffect
from .actions.attack_resolution import damage_roll_detail
from .models import AttackOutcome, PendingAttack, PendingAttackSnapshot


def snapshot_pending_attack(
    pending: PendingAttack | None,
) -> PendingAttackSnapshot | None:
    if pending is None:
        return None
    attack = pending.attack
    assert attack.damage_roll is not None
    assert attack.damage_dice is not None
    return PendingAttackSnapshot(
        action_id=pending.action_id,
        attacker_ref=pending.attacker_ref,
        target_ref=pending.target_ref,
        target_index=pending.target_index,
        attacker_label=pending.attacker_label,
        target_label=pending.target_label,
        attacks_remaining=pending.attacks_remaining,
        attack_roll=attack.attack_roll,
        attack_roll_detail=dict(attack.attack_roll_detail),
        damage_dice=attack.damage_dice,
        damage_die_rolls=[list(die.rolls) for die in attack.damage_roll.dice],
        damage_die_sides=[die.sides for die in attack.damage_roll.dice],
        damage_modifier=attack.damage_modifier,
        damage_modifier_label=attack.damage_modifier_label,
        attack_type=attack.attack_type,
        damage_type=attack.damage_type,
        critical_hit=attack.critical_hit,
        weapon_id=attack.weapon_id,
        weapon_name=attack.weapon_name,
        continuation=pending.continuation,
        reaction=pending.reaction,
        triggered_effect_id=pending.triggered_effect.id,
        triggered_effect_source_type=pending.triggered_effect.source_type,
        triggered_effect_source_id=pending.triggered_effect.source_id,
        triggered_effect_trigger=pending.triggered_effect.trigger,
        triggered_effect_operation=pending.triggered_effect.operation,
        triggered_effect_conditions=dict(pending.triggered_effect.conditions),
        triggered_effect_parameters=dict(pending.triggered_effect.parameters),
    )


def restore_pending_attack(
    snapshot: PendingAttackSnapshot | None,
) -> PendingAttack | None:
    if snapshot is None:
        return None
    dice = tuple(
        DieRollResult(sides=sides, rolls=tuple(rolls))
        for sides, rolls in zip(
            snapshot.damage_die_sides,
            snapshot.damage_die_rolls,
            strict=True,
        )
    )
    replacements = tuple(
        DieReplacement(
            die_index=index,
            previous=rolls[roll_index - 1],
            replacement=rolls[roll_index],
        )
        for index, rolls in enumerate(snapshot.damage_die_rolls)
        for roll_index in range(1, len(rolls))
    )
    subtotal = sum(die.result for die in dice)
    damage_roll = DicePoolResult(
        dice=dice,
        modifier=snapshot.damage_modifier,
        subtotal=subtotal,
        total=subtotal + snapshot.damage_modifier,
        replacements=replacements,
    )
    attack = AttackOutcome(
        messages=[],
        hit=True,
        attack_roll=snapshot.attack_roll,
        damage=max(1, damage_roll.total),
        defender_defeated=False,
        attack_roll_detail=dict(snapshot.attack_roll_detail),
        damage_roll=damage_roll,
        damage_dice=snapshot.damage_dice,
        damage_modifier=snapshot.damage_modifier,
        damage_modifier_label=snapshot.damage_modifier_label,
        attack_type=snapshot.attack_type,
        damage_type=snapshot.damage_type,
        critical_hit=snapshot.critical_hit,
        weapon_id=snapshot.weapon_id,
        weapon_name=snapshot.weapon_name,
    )
    attack.damage_roll_detail = damage_roll_detail(attack)
    return PendingAttack(
        action_id=snapshot.action_id,
        attacker_ref=snapshot.attacker_ref,
        target_ref=snapshot.target_ref,
        target_index=snapshot.target_index,
        attacker_label=snapshot.attacker_label,
        target_label=snapshot.target_label,
        attacks_remaining=snapshot.attacks_remaining,
        attack=attack,
        triggered_effect=TriggeredEffect(
            id=snapshot.triggered_effect_id,
            source_type=snapshot.triggered_effect_source_type,
            source_id=snapshot.triggered_effect_source_id,
            trigger=snapshot.triggered_effect_trigger,
            operation=snapshot.triggered_effect_operation,
            conditions=dict(snapshot.triggered_effect_conditions),
            parameters=dict(snapshot.triggered_effect_parameters),
        ),
        continuation=snapshot.continuation,
        reaction=snapshot.reaction,
    )
