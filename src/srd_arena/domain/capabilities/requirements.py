"""Predicates that constrain capability targets or resolution outcomes."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SizeRequirement:
    maximum: str | None = None
    minimum: str | None = None


@dataclass(frozen=True)
class ConditionRequirement:
    conditions: tuple[str, ...]
    match: Literal["any", "all"] = "any"
    applied_by: Literal["source", "any"] = "any"


@dataclass(frozen=True)
class CreatureTypeRequirement:
    creature_types: tuple[str, ...]


@dataclass(frozen=True)
class NotAffectedRequirement:
    action: str


@dataclass(frozen=True)
class CreatureTraitRequirement:
    trait: str


@dataclass(frozen=True)
class ConditionImmunityRequirement:
    condition: str


@dataclass(frozen=True)
class RelationshipRequirement:
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
