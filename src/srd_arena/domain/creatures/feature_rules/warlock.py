"""Resolve passive combat rules granted by Warlock subclasses."""

from __future__ import annotations

from ..model import Creature


def dark_ones_blessing_temporary_hit_points(creature: Creature) -> int | None:
    """Return the Fiend Warlock's Dark One's Blessing amount, if available.

    The current milestone supports fixed, single-class character snapshots, so
    the creature level is also its Warlock level.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     class_ref=SimpleNamespace(name="Warlock"),
    ...     character_profile=SimpleNamespace(
    ...         subclass=SimpleNamespace(name="Fiend Patron")
    ...     ),
    ...     attributes=SimpleNamespace(level=5, charisma=19),
    ...     get_modifier=lambda score: (score - 10) // 2,
    ... )
    >>> dark_ones_blessing_temporary_hit_points(creature)
    9
    """

    profile = creature.character_profile
    if (
        creature.class_ref is None
        or creature.class_ref.name.casefold() != "warlock"
        or profile is None
        or profile.subclass is None
        or profile.subclass.name.casefold() != "fiend patron"
        or creature.attributes.level < 3
    ):
        return None
    return max(
        1,
        creature.get_modifier(creature.attributes.charisma)
        + creature.attributes.level,
    )
