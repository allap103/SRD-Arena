"""Resolve combat rules granted by selected feats."""

from srd_arena.domain.effects.triggered import TriggeredEffect

from ..character_profiles import CharacterProfile
from ..model import Creature

SAVAGE_ATTACKER_EFFECT_ID = "savage_attacker"
LUCKY_FEATURE_ID = "lucky"


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


def can_use_alert_initiative_swap(creature: Creature) -> bool:
    """Return whether the creature owns Alert's post-roll swap option."""

    return creature_has_feat(creature, "Alert")


def has_lucky(creature: Creature) -> bool:
    """Return whether the creature owns the Lucky origin feat."""

    return creature_has_feat(creature, "Lucky")


def feat_maximum_health_bonus(creature: Creature) -> int:
    """Return the intrinsic maximum-HP bonus granted by selected feats.

    Tough grants 2 Hit Points for every character level, including levels
    gained before the feat was selected.

    >>> from types import SimpleNamespace
    >>> creature = SimpleNamespace(
    ...     attributes=SimpleNamespace(level=5),
    ...     character_profile=SimpleNamespace(
    ...         feats=(SimpleNamespace(name="Tough"),)
    ...     ),
    ... )
    >>> feat_maximum_health_bonus(creature)
    10
    """

    return 2 * creature.attributes.level if creature_has_feat(creature, "Tough") else 0


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
