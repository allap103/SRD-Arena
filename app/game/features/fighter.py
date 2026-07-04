from __future__ import annotations

from ..models.actor import Actor
from .types import CapabilityActionResult, DiceRoller, EffectResult


def resolve_fighter_feature(
    actor: Actor,
    feature_id: str,
    roll_dice: DiceRoller,
) -> CapabilityActionResult | None:
    if feature_id == "second_wind":
        return _resolve_second_wind(actor, roll_dice)
    if feature_id == "action_surge":
        return _resolve_action_surge(actor)
    return None


def _resolve_second_wind(actor: Actor, roll_dice: DiceRoller) -> CapabilityActionResult:
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
    return CapabilityActionResult(
        capability_id="second_wind",
        capability_name="Second Wind",
        messages=[
            ("system", f"{actor.name} uses Second Wind."),
            (
                "system",
                f"Healing: {dice_expression}={dice_total} + level {actor.attributes.level} "
                f"= {healing_total}; applied {applied_healing}.",
            ),
        ],
        effects=[
            EffectResult(
                kind="healing",
                target_ref="player",
                data={
                    "amount": applied_healing,
                    "target_label": actor.name,
                    "roll": roll_detail,
                },
            )
        ],
        resource_updates={"second_wind": actor.feature_uses_remaining["second_wind"]},
    )


def _resolve_action_surge(actor: Actor) -> CapabilityActionResult:
    actor.feature_uses_remaining["action_surge"] = (
        actor.feature_uses_remaining.get("action_surge", 0) - 1
    )
    return CapabilityActionResult(
        capability_id="action_surge",
        capability_name="Action Surge",
        messages=[
            ("system", f"{actor.name} uses Action Surge."),
            ("system", "You steel yourself and gain an additional Action this turn."),
        ],
        effects=[],
        resource_updates={"action_surge": actor.feature_uses_remaining["action_surge"]},
        details={"grant_actions": 1},
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
