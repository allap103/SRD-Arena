"""Apply rolled spell damage to one target and record structured details."""

from dataclasses import dataclass

from ...capabilities import AttackResolution
from .context import SpellTargetContext
from .preparation import PreparedSpellResolution
from .target_rolls import TargetRollOutcome


@dataclass
class TargetDamageResult:
    """Collect damage applied to one target and its structured roll details."""

    total_applied: int
    details: list[dict[str, object]]


def apply_target_damage(
    target: SpellTargetContext,
    prepared: PreparedSpellResolution,
    roll_outcome: TargetRollOutcome,
) -> TargetDamageResult:
    """Apply target damage."""

    total_applied = 0
    details: list[dict[str, object]] = []
    for damage, roll in roll_outcome.damage_rolls:
        final_damage = roll.total
        if roll_outcome.successful_save:
            final_damage = final_damage // 2 if prepared.half_damage_on_save else 0
        if isinstance(prepared.resolution, AttackResolution) and not roll_outcome.hit:
            final_damage = 0
        applied = target.creature.take_damage(final_damage, damage.damage_type)
        total_applied += applied
        details.append(
            {
                "target_ref": target.target_ref,
                "target_label": target.target_label,
                "dice": f"{len(roll.dice)}d{roll.dice[0].sides}",
                "dice_values": [die.result for die in roll.dice],
                "dice_total": roll.subtotal,
                "modifier": roll.modifier,
                "total": roll.total,
                "damage_type": damage.damage_type,
                "saved": roll_outcome.successful_save,
                "final_damage": final_damage,
                "applied_damage": applied,
            }
        )
    return TargetDamageResult(total_applied=total_applied, details=details)
