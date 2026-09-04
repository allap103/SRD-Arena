"""Map class-feature identifiers to their Python rule handlers."""

from __future__ import annotations

from collections.abc import Callable

from srd_arena.domain.effects.results import ActionResolutionResult
from srd_arena.domain.rolls.dice import DieRoller
from srd_arena.domain.spells import SpellInvocationGrant

from ..model import Creature
from .barbarian import resolve_barbarian_feature
from .fighter import resolve_fighter_feature
from .warlock import warlock_spell_invocation_grants

CLASS_FEATURE_RESOLVERS = {
    "barbarian": resolve_barbarian_feature,
    "fighter": resolve_fighter_feature,
}

SPELL_INVOCATION_GRANT_PROVIDERS = {
    "warlock": warlock_spell_invocation_grants,
}


def spell_invocation_grants(
    creature: Creature,
) -> tuple[SpellInvocationGrant, ...]:
    """Return alternate spell invocations granted by the creature's class.

    Encounter code asks this source-neutral registry rather than naming a
    particular class. New class implementations can therefore supply grants
    without changing spell discovery or execution.
    """

    class_name = (
        creature.class_ref.name.casefold() if creature.class_ref is not None else ""
    )
    provider = SPELL_INVOCATION_GRANT_PROVIDERS.get(class_name)
    return provider(creature) if provider is not None else ()


def spell_invocation_grant(
    creature: Creature,
    grant_id: str | None,
) -> SpellInvocationGrant | None:
    """Resolve one currently authoritative feature grant by stable ID."""

    if grant_id is None:
        return None
    return next(
        (grant for grant in spell_invocation_grants(creature) if grant.id == grant_id),
        None,
    )


def resolve_feature_action(
    creature: Creature,
    feature_id: str,
    roll_die: DieRoller,
    heal: Callable[[int], int],
    *,
    actor_ref: str,
    round_number: int = 1,
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
        round_number=round_number,
    )
