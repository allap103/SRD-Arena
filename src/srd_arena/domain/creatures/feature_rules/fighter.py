"""Implement fighter-specific feature mechanics that remain clearer in Python."""

from __future__ import annotations

from collections.abc import Callable

from srd_arena.domain.effects.results import (
    ActionResolutionResult,
    EffectResult,
    FeatureResolutionDetails,
)
from srd_arena.domain.rolls.dice import DieRoller, resolve_dice

from ..model import Creature


def resolve_fighter_feature(
    creature: Creature,
    feature_id: str,
    roll_die: DieRoller,
    heal: Callable[[int], int],
    *,
    actor_ref: str,
) -> ActionResolutionResult | None:
    """Execute the supported fighter feature identified by an action grant.

    >>> from ..attributes import Attributes
    >>> from ..equipment import Equipment
    >>> from ..inventory import Inventory
    >>> fighter = Creature(
    ...     "fighter", "Fighter", "", Inventory(),
    ...     Attributes(20, 1, 10, 10, 10, 10, 10, 10, 10), Equipment(),
    ...     feature_uses_remaining={"action_surge": 1},
    ... )
    >>> result = resolve_fighter_feature(
    ...     fighter, "action_surge", lambda sides: sides, fighter.heal,
    ...     actor_ref="participant:fighter",
    ... )
    >>> (result.details.granted_actions, fighter.feature_uses_remaining)
    (1, {'action_surge': 0})
    """

    if feature_id == "second_wind":
        return _resolve_second_wind(
            creature,
            roll_die,
            heal,
            actor_ref=actor_ref,
        )
    if feature_id == "action_surge":
        return _resolve_action_surge(creature)
    return None


def _resolve_second_wind(
    creature: Creature,
    roll_die: DieRoller,
    heal: Callable[[int], int],
    *,
    actor_ref: str,
) -> ActionResolutionResult:
    dice_count, dice_sides = _feature_healing_dice(creature, "second_wind")
    roll = resolve_dice(
        dice_count,
        dice_sides,
        modifier=creature.attributes.level,
        roller=roll_die,
    )
    dice_total = roll.subtotal
    healing_total = roll.total
    applied_healing = heal(healing_total)
    creature.feature_uses_remaining["second_wind"] = (
        creature.feature_uses_remaining.get("second_wind", 0) - 1
    )
    dice_expression = f"{dice_count}d{dice_sides}"
    roll_detail = {
        "dice": dice_expression,
        "dice_values": [die.result for die in roll.dice],
        "die_rolls": [list(die.rolls) for die in roll.dice],
        "dice_total": dice_total,
        "modifier": creature.attributes.level,
        "total": healing_total,
        "applied_healing": applied_healing,
    }
    return ActionResolutionResult(
        definition_id="second_wind",
        definition_name="Second Wind",
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
                target_ref=actor_ref,
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


def _resolve_action_surge(creature: Creature) -> ActionResolutionResult:
    creature.feature_uses_remaining["action_surge"] = (
        creature.feature_uses_remaining.get("action_surge", 0) - 1
    )
    return ActionResolutionResult(
        definition_id="action_surge",
        definition_name="Action Surge",
        messages=[
            ("system", f"{creature.name} uses Action Surge."),
            ("system", "You steel yourself and gain an additional Action this turn."),
        ],
        effects=[],
        resource_updates={
            "action_surge": creature.feature_uses_remaining["action_surge"]
        },
        details=FeatureResolutionDetails(granted_actions=1),
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
