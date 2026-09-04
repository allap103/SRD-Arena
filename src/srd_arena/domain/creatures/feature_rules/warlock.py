"""Resolve passive combat rules granted by Warlock subclasses."""

from __future__ import annotations

from srd_arena.domain.spells import SpellInvocationGrant

from ..model import Creature

FIENDISH_VIGOR_GRANT_ID = "fiendish_vigor"


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
        creature.get_modifier(creature.attributes.charisma) + creature.attributes.level,
    )


def warlock_spell_invocation_grants(
    creature: Creature,
) -> tuple[SpellInvocationGrant, ...]:
    """Return alternate spell invocations supplied by Warlock features.

    Fiendish Vigor grants a level-1, slot-free casting of False Life on the
    Warlock. Its temporary-Hit-Point dice use their maximum result.
    """

    profile = creature.character_profile
    if (
        creature.class_ref is None
        or creature.class_ref.name.casefold() != "warlock"
        or creature.attributes.level < 2
        or profile is None
        or not any(
            feature.name.casefold() == "fiendish vigor"
            for feature in profile.selected_features
        )
    ):
        return ()
    return (
        SpellInvocationGrant(
            id=FIENDISH_VIGOR_GRANT_ID,
            spell_id="false_life",
            source_name="Fiendish Vigor",
            fixed_cast_level=1,
            consumes_spell_slot=False,
            temporary_hit_point_dice="maximum",
        ),
    )
