"""Formatting helpers for structured spell-resolution details."""

from ...capabilities import EffectDuration, RollModifierEffect
from ...rolls.dice import DicePoolResult, resolve_dice
from .context import DieRoller, SpellTargetContext
from .scaling import parse_damage_dice


def roll_optional_dice(
    dice: str | None,
    roller: DieRoller,
) -> DicePoolResult | None:
    """Resolve an optional dice expression, returning no roll when absent."""

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
    """Build the stable event payload for healing or temporary Hit Points."""

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


def serialize_roll_modifiers(
    modifiers: tuple[RollModifierEffect, ...],
    selected_ability: str | None,
) -> list[dict[str, object]]:
    """Expose the sources and totals of roll modifiers in event-safe form."""

    serialized: list[dict[str, object]] = []
    for modifier in modifiers:
        abilities = modifier.ability_options or (modifier.ability,)
        for ability in abilities:
            if ability is not None and ability != selected_ability:
                continue
            rolls = (
                ("ability_check", "attack_roll", "saving_throw")
                if modifier.roll == "d20_test"
                else (modifier.roll,)
            )
            serialized.extend(
                {
                    "roll": roll,
                    "mode": modifier.mode,
                    "dice": modifier.dice,
                    "value": modifier.value,
                    "subject": modifier.subject,
                    "ignored_by_senses": list(modifier.ignored_by_senses),
                    "ability": ability,
                }
                for roll in rolls
            )
    return serialized


def effect_duration_rounds(duration: EffectDuration | None) -> int | None:
    """Convert a capability duration into encounter rounds when possible."""

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
