"""Map class-feature identifiers to their Python rule handlers."""

from __future__ import annotations

from collections.abc import Callable

from ..model import Creature
from .fighter import resolve_fighter_feature
from .types import CapabilityActionResult, DiceRoller, HealingReceiver

FeatureResolver = Callable[
    [Creature, str, DiceRoller, HealingReceiver],
    CapabilityActionResult | None,
]

CLASS_FEATURE_RESOLVERS: dict[str, FeatureResolver] = {
    "fighter": resolve_fighter_feature,
}


def resolve_feature_action(
    creature: Creature,
    feature_id: str,
    roll_dice: DiceRoller,
    heal: HealingReceiver,
) -> CapabilityActionResult | None:
    """Dispatch a feature identifier to the domain handler registered for it.

    >>> from ..attributes import Attributes
    >>> from ..classes import ClassRef
    >>> from ..equipment import Equipment
    >>> from ..inventory import Inventory
    >>> fighter = Creature(
    ...     "fighter", "Fighter", "", Inventory(),
    ...     Attributes(20, 1, 10, 10, 10, 10, 10, 10, 10), Equipment(),
    ...     class_ref=ClassRef("Fighter"),
    ...     feature_uses_remaining={"action_surge": 1},
    ... )
    >>> result = resolve_feature_action(
    ...     fighter, "action_surge", lambda count, sides: count, fighter.heal
    ... )
    >>> result.capability_name if result else None
    'Action Surge'
    """

    class_name = (
        creature.class_ref.name.casefold() if creature.class_ref is not None else ""
    )
    class_resolver = CLASS_FEATURE_RESOLVERS.get(class_name)
    if class_resolver is None:
        return None
    return class_resolver(creature, feature_id, roll_dice, heal)
