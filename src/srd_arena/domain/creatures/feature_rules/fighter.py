from __future__ import annotations

from ...effects.results import EffectResult
from ..model import Creature
from .types import CapabilityActionResult, DiceRoller


def resolve_fighter_feature(
    creature: Creature,
    feature_id: str,
    roll_dice: DiceRoller,
) -> CapabilityActionResult | None:
    if feature_id == "second_wind":
        return _resolve_second_wind(creature, roll_dice)
    if feature_id == "action_surge":
        return _resolve_action_surge(creature)
    return None


def _resolve_second_wind(
    creature: Creature, roll_dice: DiceRoller
) -> CapabilityActionResult:
    dice_count, dice_sides = _feature_healing_dice(creature, "second_wind")
    dice_total = roll_dice(dice_count, dice_sides)
    healing_total = dice_total + creature.attributes.level
    applied_healing = creature.heal(healing_total)
    creature.feature_uses_remaining["second_wind"] = (
        creature.feature_uses_remaining.get("second_wind", 0) - 1
    )
    dice_expression = f"{dice_count}d{dice_sides}"
    roll_detail = {
        "dice": dice_expression,
        "dice_total": dice_total,
        "modifier": creature.attributes.level,
        "total": healing_total,
        "applied_healing": applied_healing,
    }
    return CapabilityActionResult(
        capability_id="second_wind",
        capability_name="Second Wind",
        messages=[
            ("system", f"{creature.name} uses Second Wind."),
            (
                "system",
                f"Healing: {dice_expression}={dice_total} + level {creature.attributes.level} "
                f"= {healing_total}; applied {applied_healing}.",
            ),
        ],
        effects=[
            EffectResult(
                kind="healing",
                target_ref="player",
                data={
                    "amount": applied_healing,
                    "target_label": creature.name,
                    "roll": roll_detail,
                },
            )
        ],
        resource_updates={
            "second_wind": creature.feature_uses_remaining["second_wind"]
        },
    )


def _resolve_action_surge(creature: Creature) -> CapabilityActionResult:
    creature.feature_uses_remaining["action_surge"] = (
        creature.feature_uses_remaining.get("action_surge", 0) - 1
    )
    return CapabilityActionResult(
        capability_id="action_surge",
        capability_name="Action Surge",
        messages=[
            ("system", f"{creature.name} uses Action Surge."),
            ("system", "You steel yourself and gain an additional Action this turn."),
        ],
        effects=[],
        resource_updates={
            "action_surge": creature.feature_uses_remaining["action_surge"]
        },
        details={"grant_actions": 1},
    )


def _feature_healing_dice(creature: Creature, feature_id: str) -> tuple[int, int]:
    class_feature = next(
        (
            class_feature
            for class_feature in creature.class_features
            if class_feature.id == feature_id
        ),
        None,
    )
    if class_feature is None:
        return 1, 10
    dice_count = class_feature.data.get("healing_die_count")
    dice_sides = class_feature.data.get("healing_die_sides")
    if not isinstance(dice_count, int) or not isinstance(dice_sides, int):
        return 1, 10
    return dice_count, dice_sides
