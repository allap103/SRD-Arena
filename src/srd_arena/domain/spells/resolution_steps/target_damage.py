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
    """Apply resolved spell damage after immunity, resistance, and save scaling.

    >>> from types import SimpleNamespace
    >>> from ...capabilities import AutomaticResolution, Outcome
    >>> from ...rolls.dice import DicePoolResult, DieRollResult
    >>> from ..definitions import SpellDamage
    >>> roll = DicePoolResult((DieRollResult(6, (4,)),), 0, 4, 4)
    >>> outcome = TargetRollOutcome(
    ...     False, (), True, [(SpellDamage("1d6", "fire"), roll)]
    ... )
    >>> target = SimpleNamespace(
    ...     target_ref="goblin", target_label="Goblin",
    ...     creature=SimpleNamespace(take_damage=lambda amount, kind: amount),
    ... )
    >>> prepared = SimpleNamespace(
    ...     half_damage_on_save=False, resolution=AutomaticResolution(Outcome())
    ... )
    >>> result = apply_target_damage(target, prepared, outcome)
    >>> (result.total_applied, result.details[0]["damage_type"])
    (4, 'fire')
    """

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
