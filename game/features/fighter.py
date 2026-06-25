from __future__ import annotations

from ..models.actor import Actor
from .types import DiceRoller, FeatureActionResult


def resolve_fighter_feature(
    actor: Actor,
    feature_id: str,
    roll_dice: DiceRoller,
) -> FeatureActionResult | None:
    if feature_id == "second_wind":
        return _resolve_second_wind(actor, roll_dice)
    return None


def _resolve_second_wind(actor: Actor, roll_dice: DiceRoller) -> FeatureActionResult:
    dice_count, dice_sides = _feature_healing_dice(actor, "second_wind")
    dice_total = roll_dice(dice_count, dice_sides)
    healing_total = dice_total + actor.attributes.level
    applied_healing = actor.heal(healing_total)
    actor.feature_uses_remaining["second_wind"] = (
        actor.feature_uses_remaining.get("second_wind", 0) - 1
    )
    dice_expression = f"{dice_count}d{dice_sides}"
    roll_detail = {
        "dice": dice_expression,
        "dice_total": dice_total,
        "modifier": actor.attributes.level,
        "total": healing_total,
        "applied_healing": applied_healing,
    }
    return FeatureActionResult(
        feature_id="second_wind",
        feature_name="Second Wind",
        target_label=actor.name,
        healing=applied_healing,
        roll_detail=roll_detail,
        uses_remaining=actor.feature_uses_remaining["second_wind"],
        messages=[
            ("system", f"{actor.name} uses Second Wind."),
            (
                "system",
                f"Healing: {dice_expression}={dice_total} + level {actor.attributes.level} "
                f"= {healing_total}; applied {applied_healing}.",
            ),
        ],
    )


def _feature_healing_dice(actor: Actor, feature_id: str) -> tuple[int, int]:
    grant = next((grant for grant in actor.feature_grants if grant.id == feature_id), None)
    if grant is None:
        return 1, 10
    dice_count = grant.data.get("healing_die_count")
    dice_sides = grant.data.get("healing_die_sides")
    if not isinstance(dice_count, int) or not isinstance(dice_sides, int):
        return 1, 10
    return dice_count, dice_sides
