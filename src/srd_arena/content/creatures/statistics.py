"""Derive domain combat statistics from authored creature values."""

from fractions import Fraction

from srd_arena.domain.creatures import CreatureStatistics
from srd_arena.domain.effects.conditions import Condition

from .stat_block_schema import BestiaryMonsterSchema

ABILITY_NAMES = {
    "str": "strength",
    "dex": "dexterity",
    "con": "constitution",
    "int": "intelligence",
    "wis": "wisdom",
    "cha": "charisma",
}


def build_creature_statistics(
    stat_block: BestiaryMonsterSchema | None,
) -> CreatureStatistics:
    """Translate authored AC, hit points, challenge, and save bonuses into domain state."""

    if stat_block is None:
        return CreatureStatistics()
    return CreatureStatistics(
        creature_type=stat_block.creature_type,
        type_tags=stat_block.type_tags,
        alignment=tuple(
            value for value in stat_block.alignment if isinstance(value, str)
        ),
        challenge_rating=stat_block.challenge_rating,
        saving_throw_bonuses={
            ABILITY_NAMES.get(name.casefold(), name.casefold()): _parse_bonus(value)
            for name, value in stat_block.save.items()
        },
        skill_bonuses={
            name.casefold(): _parse_bonus(value)
            for name, value in stat_block.skill.items()
        },
        senses=tuple(stat_block.senses),
        passive_perception=stat_block.passive,
        languages=tuple(stat_block.languages),
        condition_immunities=frozenset(
            Condition(condition.casefold())
            for condition in stat_block.condition_immune
            if isinstance(condition, str)
        ),
        mechanical_traits=frozenset(stat_block.mechanical_traits),
    )


def challenge_rating_proficiency_bonus(challenge_rating: str | None) -> int:
    """Convert an SRD challenge rating into its proficiency bonus."""

    if challenge_rating is None:
        return 2
    rating = Fraction(challenge_rating)
    return 2 + max(0, (rating.numerator // rating.denominator - 1) // 4)


def _parse_bonus(value: str) -> int:
    return int(value.strip())
