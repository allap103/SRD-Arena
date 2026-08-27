"""Predicates that constrain capability targets or resolution outcomes."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SizeRequirement:
    """Restrict a target to an inclusive creature-size range."""

    maximum: str | None = None
    minimum: str | None = None


@dataclass(frozen=True)
class ConditionRequirement:
    """Require target conditions, optionally applied by this capability's source."""

    conditions: tuple[str, ...]
    match: Literal["any", "all"] = "any"
    applied_by: Literal["source", "any"] = "any"


@dataclass(frozen=True)
class CreatureTypeRequirement:
    """Restrict a capability to one of the listed creature types."""

    creature_types: tuple[str, ...]


@dataclass(frozen=True)
class NotAffectedRequirement:
    """Require that the target is not already affected by a named action."""

    action: str


@dataclass(frozen=True)
class CreatureTraitRequirement:
    """Require a named mechanical trait on the target creature."""

    trait: str


@dataclass(frozen=True)
class ConditionImmunityRequirement:
    """Require the target to possess immunity to a named condition."""

    condition: str


@dataclass(frozen=True)
class RelationshipRequirement:
    """Require a directional creature relationship with constrained provenance."""

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
