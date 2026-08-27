"""Predicates that constrain capability targets or resolution outcomes."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SizeRequirement:
    """Represent a size requirement."""

    maximum: str | None = None
    minimum: str | None = None


@dataclass(frozen=True)
class ConditionRequirement:
    """Represent a condition requirement."""

    conditions: tuple[str, ...]
    match: Literal["any", "all"] = "any"
    applied_by: Literal["source", "any"] = "any"


@dataclass(frozen=True)
class CreatureTypeRequirement:
    """Represent a creature type requirement."""

    creature_types: tuple[str, ...]


@dataclass(frozen=True)
class NotAffectedRequirement:
    """Represent a not affected requirement."""

    action: str


@dataclass(frozen=True)
class CreatureTraitRequirement:
    """Represent a creature trait requirement."""

    trait: str


@dataclass(frozen=True)
class ConditionImmunityRequirement:
    """Represent a condition immunity requirement."""

    condition: str


@dataclass(frozen=True)
class RelationshipRequirement:
    """Represent a relationship requirement."""

    relationship: str
    established_by: Literal["this_spell", "source", "any"] = "any"


CapabilityRequirement = (
    SizeRequirement
    | ConditionRequirement
    | CreatureTypeRequirement
    | NotAffectedRequirement
    | CreatureTraitRequirement
    | ConditionImmunityRequirement
    | RelationshipRequirement
)
