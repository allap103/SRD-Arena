from srd_arena.domain.effects.triggered import TriggeredEffect

from .optional_feature_schema import OptionalFeatureSchema


def normalize_optional_feature_effects(
    feature: OptionalFeatureSchema,
) -> list[TriggeredEffect]:
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
