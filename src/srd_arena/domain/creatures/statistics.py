"""Store descriptive and rules-relevant statistics beyond ability scores."""

from dataclasses import dataclass, field

from srd_arena.domain.effects.conditions import Condition


@dataclass(frozen=True)
class CreatureStatistics:
    """Hold creature type, proficiencies, senses, immunities, and mechanical traits."""

    creature_type: str | None = None
    type_tags: tuple[str, ...] = ()
    alignment: tuple[str, ...] = ()
    challenge_rating: str | None = None
    initiative_proficiency_multiplier: int = 0
    saving_throw_bonuses: dict[str, int] = field(default_factory=dict)
    skill_bonuses: dict[str, int] = field(default_factory=dict)
    senses: tuple[str, ...] = ()
    passive_perception: int | None = None
    languages: tuple[str, ...] = ()
    condition_immunities: frozenset[Condition] = frozenset()
    damage_resistances: frozenset[str] = frozenset()
    damage_immunities: frozenset[str] = frozenset()
    damage_vulnerabilities: frozenset[str] = frozenset()
    mechanical_traits: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        """Normalize authored damage types for case-insensitive rule queries.

        >>> statistics = CreatureStatistics(
        ...     damage_resistances=frozenset({"Fire"}),
        ...     damage_immunities=frozenset({"POISON"}),
        ...     damage_vulnerabilities=frozenset({"Bludgeoning"}),
        ... )
        >>> statistics.damage_immunities
        frozenset({'poison'})
        """

        for field_name in (
            "damage_resistances",
            "damage_immunities",
            "damage_vulnerabilities",
        ):
            values = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                frozenset(value.casefold() for value in values),
            )
