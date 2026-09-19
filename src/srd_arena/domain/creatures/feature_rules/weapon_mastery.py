"""Resolve which authored weapon mastery a creature can currently use."""

from srd_arena.domain.equipment import Item

from ..model import Creature

WEAPON_MASTERY_FEATURE_ID = "weapon_mastery"


def selected_weapon_mastery(creature: Creature, weapon: Item) -> str | None:
    """Return the weapon's mastery when this creature selected that weapon.

    A weapon carrying a mastery property is not sufficient by itself. The
    creature must both own Weapon Mastery and have selected that exact weapon.
    This function resolves identity only; post-hit mastery rules remain in the
    encounter layer where exact attack occurrences and decisions are available.

    >>> from types import SimpleNamespace
    >>> from srd_arena.domain.equipment import WeaponStat
    >>> weapon = Item(
    ...     "maul", "Maul", "", "weapon",
    ...     weapon_stat=WeaponStat([], "2d6", "bludgeoning", [], mastery="Topple"),
    ... )
    >>> creature = SimpleNamespace(
    ...     class_features=[SimpleNamespace(id="weapon_mastery")],
    ...     character_profile=SimpleNamespace(weapon_masteries=("Maul",)),
    ... )
    >>> selected_weapon_mastery(creature, weapon)
    'Topple'
    """

    weapon_stat = weapon.weapon_stat
    if weapon_stat is None or weapon_stat.mastery is None:
        return None
    if not any(
        feature.id == WEAPON_MASTERY_FEATURE_ID
        for feature in getattr(creature, "class_features", ())
    ):
        return None
    profile = getattr(creature, "character_profile", None)
    if profile is None or weapon.name.casefold() not in {
        name.casefold() for name in profile.weapon_masteries
    }:
        return None
    return weapon_stat.mastery
