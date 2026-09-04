"""Resolve combat rules granted by selected feats."""

from srd_arena.domain.effects.triggered import TriggeredEffect

from ..character_profiles import CharacterProfile
from ..model import Creature

SAVAGE_ATTACKER_EFFECT_ID = "savage_attacker"


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


def feat_triggered_effects(
    profile: CharacterProfile | None,
) -> tuple[TriggeredEffect, ...]:
    """Build executable triggered rules for supported selected feats.

    >>> from ..character_profiles import CharacterOptionRef
    >>> profile = CharacterProfile(
    ...     "hero", CharacterOptionRef("Human"), CharacterOptionRef("Soldier"),
    ...     feats=(CharacterOptionRef("Savage Attacker", "XPHB"),),
    ... )
    >>> effect = feat_triggered_effects(profile)[0]
    >>> (effect.id, effect.operation)
    ('savage_attacker', 'roll_damage_pool_twice')
    """

    if profile is None:
        return ()
    effects: list[TriggeredEffect] = []
    if any(
        feat.name.casefold() == "savage attacker"
        and (feat.source or "").upper() == "XPHB"
        for feat in profile.feats
    ):
        effects.append(
            TriggeredEffect(
                id=SAVAGE_ATTACKER_EFFECT_ID,
                source_type="feat",
                source_id="savage_attacker|xphb",
                trigger="weapon_damage_rolled",
                operation="roll_damage_pool_twice",
                conditions={"weapon": True},
                parameters={"optional": True, "maximum_per_turn": 1},
            )
        )
    return tuple(effects)
