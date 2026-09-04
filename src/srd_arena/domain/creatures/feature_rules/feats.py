"""Resolve combat rules granted by selected feats."""

from ..model import Creature


def creature_has_feat(creature: Creature, feat_name: str) -> bool:
    """Return whether a fixed character profile selected the named feat.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     character_profile=SimpleNamespace(
    ...         feats=(SimpleNamespace(name="Alert"),)
    ...     )
    ... )
    >>> creature_has_feat(creature, "alert")
    True
    """

    profile = creature.character_profile
    return bool(
        profile is not None
        and any(feat.name.casefold() == feat_name.casefold() for feat in profile.feats)
    )


def initiative_modifier(creature: Creature) -> int:
    """Return Dexterity plus any selected feat bonus used for Initiative.

    Alert grants proficiency in Initiative. The fixed milestone characters
    already carry their level-appropriate proficiency bonus.
    """

    modifier = creature.get_modifier(creature.attributes.dexterity)
    if creature_has_feat(creature, "Alert"):
        modifier += creature.attributes.proficiency_bonus
    return modifier


def can_use_alert_initiative_swap(creature: Creature) -> bool:
    """Return whether the creature owns Alert's post-roll swap option."""

    return creature_has_feat(creature, "Alert")
