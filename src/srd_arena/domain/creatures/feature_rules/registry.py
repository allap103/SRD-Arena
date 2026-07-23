from __future__ import annotations

from collections.abc import Callable

from ..model import Creature
from .fighter import resolve_fighter_feature
from .types import CapabilityActionResult, DiceRoller

FeatureResolver = Callable[[Creature, str, DiceRoller], CapabilityActionResult | None]

CLASS_FEATURE_RESOLVERS: dict[str, FeatureResolver] = {
    "fighter": resolve_fighter_feature,
}


def resolve_feature_action(
    creature: Creature,
    feature_id: str,
    roll_dice: DiceRoller,
) -> CapabilityActionResult | None:
    class_name = creature.class_ref.name.casefold() if creature.class_ref is not None else ""
    class_resolver = CLASS_FEATURE_RESOLVERS.get(class_name)
    if class_resolver is None:
        return None
    return class_resolver(creature, feature_id, roll_dice)
