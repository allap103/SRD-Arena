"""Define immutable intrinsic metadata used when a spell is cast."""

from dataclasses import dataclass
from typing import Literal

SpellCastingTimeUnit = Literal["action", "bonus", "reaction", "minute", "hour"]
SpellRangeKind = Literal["point", "cone", "cube", "emanation", "line", "sphere"]
SpellDistanceKind = Literal[
    "feet",
    "miles",
    "self",
    "sight",
    "touch",
    "unlimited",
]
SpellDurationKind = Literal["instant", "permanent", "special", "timed"]
SpellDurationUnit = Literal["round", "minute", "hour", "day"]


@dataclass(frozen=True)
class SpellCastingTime:
    """Describe one casting-time option and any prose trigger or label.

    >>> SpellCastingTime(1, "reaction", trigger="when hit").unit
    'reaction'
    """

    number: int
    unit: SpellCastingTimeUnit
    trigger: str | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        """Reject non-positive casting-time quantities."""
        if self.number <= 0:
            raise ValueError("A spell casting-time quantity must be positive.")


@dataclass(frozen=True)
class SpellRangeDistance:
    """Describe a numeric or special distance attached to a spell range.

    >>> SpellRangeDistance("feet", 60)
    SpellRangeDistance(kind='feet', amount=60)
    """

    kind: SpellDistanceKind
    amount: int | None = None

    def __post_init__(self) -> None:
        """Require amounts exactly for numeric distance kinds."""
        numeric = self.kind in {"feet", "miles"}
        if numeric and (self.amount is None or self.amount <= 0):
            raise ValueError("Numeric spell distances require a positive amount.")
        if not numeric and self.amount is not None:
            raise ValueError("Special spell distances cannot define an amount.")


@dataclass(frozen=True)
class SpellRange:
    """Pair a spell's targeting shape with its maximum distance.

    >>> SpellRange("cone", SpellRangeDistance("feet", 15)).kind
    'cone'
    """

    kind: SpellRangeKind
    distance: SpellRangeDistance


@dataclass(frozen=True)
class SpellMaterialComponent:
    """Describe a spell's material requirement and optional monetary rules.

    Costs use copper pieces, matching the normalized authored content.

    >>> SpellMaterialComponent("diamond dust", cost_copper=10_000, consumed=True)
    SpellMaterialComponent(text='diamond dust', cost_copper=10000, consumed=True)
    """

    text: str
    cost_copper: int | None = None
    consumed: bool = False

    def __post_init__(self) -> None:
        """Reject empty descriptions and non-positive stated costs."""
        if not self.text:
            raise ValueError("A material component description cannot be empty.")
        if self.cost_copper is not None and self.cost_copper <= 0:
            raise ValueError("A material component cost must be positive.")


@dataclass(frozen=True)
class SpellComponents:
    """Record which components a casting requires and material details.

    >>> sorted(SpellComponents(
    ...     verbal=True, material=SpellMaterialComponent("a pearl")
    ... ).required)
    ['material', 'verbal']
    """

    verbal: bool = False
    somatic: bool = False
    material: SpellMaterialComponent | None = None

    @property
    def required(self) -> frozenset[str]:
        """Return normalized component names used by invocation rule queries.

        >>> SpellComponents(somatic=True).required
        frozenset({'somatic'})
        """
        return frozenset(
            name
            for name, present in (
                ("verbal", self.verbal),
                ("somatic", self.somatic),
                ("material", self.material is not None),
            )
            if present
        )


@dataclass(frozen=True)
class SpellDuration:
    """Describe one intrinsic spell duration and its ending metadata.

    >>> SpellDuration("timed", amount=1, unit="minute", concentration=True)
    SpellDuration(kind='timed', amount=1, unit='minute', concentration=True, ending_events=())
    """

    kind: SpellDurationKind
    amount: int | None = None
    unit: SpellDurationUnit | None = None
    concentration: bool = False
    ending_events: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Require quantities for timed durations and reject misplaced fields."""
        if self.kind == "timed":
            if self.amount is None or self.amount <= 0 or self.unit is None:
                raise ValueError(
                    "Timed spell durations require a positive amount and unit."
                )
        elif self.amount is not None or self.unit is not None:
            raise ValueError(
                "Only timed spell durations can define an amount and unit."
            )
        if self.concentration and self.kind != "timed":
            raise ValueError("Only timed spell durations can require concentration.")
        if self.ending_events and self.kind != "permanent":
            raise ValueError("Only permanent spell durations can define ending events.")
