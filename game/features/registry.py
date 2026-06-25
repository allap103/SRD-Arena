from __future__ import annotations

from collections.abc import Callable

from ..models.actor import Actor
from .fighter import resolve_fighter_feature
from .types import DiceRoller, FeatureActionResult

FeatureResolver = Callable[[Actor, str, DiceRoller], FeatureActionResult | None]

CLASS_FEATURE_RESOLVERS: dict[str, FeatureResolver] = {
    "fighter": resolve_fighter_feature,
}


def resolve_feature_action(
    actor: Actor,
    feature_id: str,
    roll_dice: DiceRoller,
) -> FeatureActionResult | None:
    class_name = actor.class_ref.name.casefold() if actor.class_ref is not None else ""
    class_resolver = CLASS_FEATURE_RESOLVERS.get(class_name)
    if class_resolver is None:
        return None
    return class_resolver(actor, feature_id, roll_dice)
