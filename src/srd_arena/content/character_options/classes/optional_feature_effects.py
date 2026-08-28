"""Apply supported optional-feature changes while building a creature."""

from srd_arena.domain.effects.triggered import TriggeredEffect

from .optional_feature_schema import OptionalFeatureSchema


def normalize_optional_feature_effects(
    feature: OptionalFeatureSchema,
) -> list[TriggeredEffect]:
    """Convert supported optional features into stable triggered effects.

    >>> feature = OptionalFeatureSchema(
    ...     name="Great Weapon Fighting", source="PHB")
    >>> effect = normalize_optional_feature_effects(feature)[0]
    >>> (effect.trigger, effect.parameters["values"])
    ('weapon_damage_rolled', [1, 2])
    >>> normalize_optional_feature_effects(
    ...     OptionalFeatureSchema(name="Unknown", source="X"))
    []
    """

    name = feature.public_name
    source = feature.source
    canonical_id = f"{name.casefold().replace(' ', '_')}|{source.casefold()}"
    if (name.casefold(), source.upper()) == ("great weapon fighting", "PHB"):
        return [
            TriggeredEffect(
                id="great_weapon_fighting",
                source_type="fighting_style",
                source_id=canonical_id,
                trigger="weapon_damage_rolled",
                operation="reroll_matching_dice",
                conditions={
                    "attack_type": "melee",
                    "wielded_with": "two_hands",
                    "weapon_properties_any": ["two-handed", "versatile"],
                },
                parameters={
                    "values": [1, 2],
                    "maximum_per_die": 1,
                    "must_use_replacement": True,
                    "optional": True,
                },
            )
        ]
    return []
