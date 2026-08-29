"""Formatting helpers for structured spell-resolution details."""

from srd_arena.domain.capabilities import EffectDuration
from srd_arena.domain.rolls.dice import DicePoolResult, DieRoller, resolve_dice

from .context import SpellTargetContext
from .scaling import parse_damage_dice


def roll_optional_dice(
    dice: str | None,
    roller: DieRoller,
) -> DicePoolResult | None:
    """Resolve an optional dice expression, returning no roll when absent.

    >>> roll = roll_optional_dice("2d6", lambda sides: 4)
    >>> (roll.subtotal, roll.total) if roll else None
    (8, 8)
    >>> roll_optional_dice(None, lambda sides: 4) is None
    True
    """

    if dice is None:
        return None
    count, sides = parse_damage_dice(dice)
    return resolve_dice(count, sides, roller=roller)


def restoration_detail(
    target: SpellTargetContext,
    *,
    dice: str | None,
    roll: DicePoolResult | None,
    modifier: int,
    total: int,
    applied: int,
) -> dict[str, object]:
    """Build the stable event payload for healing or temporary Hit Points.

    >>> from types import SimpleNamespace
    >>> target = SimpleNamespace(target_ref="hero", target_label="Hero")
    >>> detail = restoration_detail(
    ...     target, dice=None, roll=None, modifier=5, total=5, applied=3
    ... )
    >>> (detail["target_ref"], detail["total"], detail["applied"])
    ('hero', 5, 3)
    """

    return {
        "target_ref": target.target_ref,
        "target_label": target.target_label,
        "dice": dice,
        "dice_values": [die.result for die in roll.dice] if roll is not None else [],
        "dice_total": roll.subtotal if roll is not None else 0,
        "modifier": modifier,
        "total": total,
        "applied": applied,
    }


def effect_duration_rounds(duration: EffectDuration | None) -> int | None:
    """Convert a capability duration into encounter rounds when possible.

    >>> effect_duration_rounds(EffectDuration("timed", 2, "minute"))
    20
    >>> effect_duration_rounds(EffectDuration("end_of_turn"))
    1
    """

    if duration is None:
        return None
    if duration.kind in {"start_of_turn", "end_of_turn"}:
        return 1
    rounds_per_unit = {
        "round": 1,
        "minute": 10,
        "hour": 600,
        "day": 14_400,
    }
    if duration.kind != "timed" or duration.amount is None:
        return None
    multiplier = rounds_per_unit.get(duration.unit or "")
    return duration.amount * multiplier if multiplier is not None else None
