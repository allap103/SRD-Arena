"""Encode disclosed spell descriptors using a versioned semantic vocabulary."""

from functools import lru_cache

from srd_arena.engine.api import SpellCapabilityObservation

from .mechanics_encoding import MECHANIC_FEATURES, mechanics_features

SPELL_IDS = (
    "eldritch_blast",
    "mind_sliver",
    "hex",
    "hideous_laughter",
    "armor_of_agathys",
    "hold_person",
    "misty_step",
    "hypnotic_pattern",
    "burning_hands",
    "command",
    "scorching_ray",
    "fireball",
    "stinking_cloud",
    "false_life",
    "slow",
)
SPELL_CATEGORIES = {
    "spell_id": SPELL_IDS,
    "range_kind": ("feet", "self", "touch", "unlimited", "sight"),
    "target_kind": ("self", "creature", "area", "point"),
    "area_shape": ("cone", "cube", "sphere", "line", "radius", "cylinder"),
    "resolution_kind": ("automatic", "attack", "saving_throw"),
    "save_ability": (
        "strength",
        "dexterity",
        "constitution",
        "intelligence",
        "wisdom",
        "charisma",
    ),
    "custom_resolver_id": ("slow", "stinking_cloud"),
    "temporary_hit_point_dice": ("roll", "maximum"),
}
SPELL_NUMBERS = {
    "spell_level": 9,
    "cast_level": 9,
    "action_cost": 1,
    "bonus_action_cost": 1,
    "reaction_cost": 1,
    "spell_slot_cost": 1,
    "range_amount": 120,
    "maximum_targets": 10,
    "area_size_feet": 60,
    "attack_bonus": 20,
    "save_dc": 30,
}
SPELL_FEATURES = (
    *MECHANIC_FEATURES,
    "spell_known",
    "spell_concentration",
    *(
        f"spell_{field}_{value}"
        for field, values in SPELL_CATEGORIES.items()
        for value in (*values, "unknown")
    ),
    *(f"spell_{field}{suffix}" for field in SPELL_NUMBERS for suffix in ("", "_known")),
)


@lru_cache(maxsize=512)
def spell_features(spell: SpellCapabilityObservation | None) -> tuple[float, ...]:
    """Return zeros for undisclosed mechanics, with explicit known/unknown flags."""
    if spell is None:
        return (0.0,) * len(SPELL_FEATURES)
    values = [*mechanics_features(spell), 1.0, float(spell.concentration)]
    for field, categories in SPELL_CATEGORIES.items():
        value = getattr(spell, field)
        values.extend(float(value == category) for category in categories)
        values.append(float(value not in categories))
    for field, scale in SPELL_NUMBERS.items():
        value = getattr(spell, field)
        values.extend(
            (value / scale if value is not None else 0.0, float(value is not None))
        )
    return tuple(values)
