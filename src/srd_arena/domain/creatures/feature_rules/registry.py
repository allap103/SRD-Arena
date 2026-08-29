"""Map class-feature identifiers to their Python rule handlers."""

from __future__ import annotations

from typing import Protocol

from ...effects.results import ActionResolutionResult
from ...rolls.dice import DieRoller
from ..model import Creature
from .contracts import HealingReceiver
from .fighter import resolve_fighter_feature


class FeatureResolver(Protocol):
    """Resolve one class feature for an explicitly identified encounter actor."""

    def __call__(
        self,
        creature: Creature,
        feature_id: str,
        roll_die: DieRoller,
        heal: HealingReceiver,
        *,
        actor_ref: str,
    ) -> ActionResolutionResult | None: ...


CLASS_FEATURE_RESOLVERS: dict[str, FeatureResolver] = {
    "fighter": resolve_fighter_feature,
}


def resolve_feature_action(
    creature: Creature,
    feature_id: str,
    roll_die: DieRoller,
    heal: HealingReceiver,
    *,
    actor_ref: str,
) -> ActionResolutionResult | None:
    """Dispatch a feature with the acting encounter participant's identity.

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
    ...     fighter, "action_surge", lambda sides: sides, fighter.heal,
    ...     actor_ref="participant:fighter",
    ... )
    >>> result.definition_name if result else None
    'Action Surge'
    """

    class_name = (
        creature.class_ref.name.casefold() if creature.class_ref is not None else ""
    )
    class_resolver = CLASS_FEATURE_RESOLVERS.get(class_name)
    if class_resolver is None:
        return None
    return class_resolver(
        creature,
        feature_id,
        roll_die,
        heal,
        actor_ref=actor_ref,
    )
