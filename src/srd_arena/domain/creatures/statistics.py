"""Store descriptive and rules-relevant statistics beyond ability scores."""

from dataclasses import dataclass, field

from ..effects.conditions import Condition


@dataclass(frozen=True)
class CreatureStatistics:
    """Hold creature type, proficiencies, senses, immunities, and mechanical traits."""

    creature_type: str | None = None
    type_tags: tuple[str, ...] = ()
    alignment: tuple[str, ...] = ()
    challenge_rating: str | None = None
    saving_throw_bonuses: dict[str, int] = field(default_factory=dict)
    skill_bonuses: dict[str, int] = field(default_factory=dict)
    senses: tuple[str, ...] = ()
    passive_perception: int | None = None
    languages: tuple[str, ...] = ()
    condition_immunities: frozenset[Condition] = frozenset()
    mechanical_traits: frozenset[str] = frozenset()
