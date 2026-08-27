"""Provide runtime support for the effects package."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .rule_effects import RuntimeRuleEffect


class EffectSourceKind(StrEnum):
    """Enumerate supported effect source kind values."""

    CREATURE = "creature"
    ACTION = "action"
    SPELL = "spell"
    FEATURE = "feature"
    ITEM = "item"
    ENVIRONMENT = "environment"
    SYSTEM = "system"


@dataclass(frozen=True)
class EffectSource:
    """Represent an effect source."""

    kind: EffectSourceKind
    definition_id: str
    applied_by_ref: str | None = None
    label: str | None = None
    origin_id: str = ""


@dataclass(frozen=True)
class RuntimeStateIdentity:
    """Represent a runtime state identity."""

    id: str
    source: EffectSource
    parent_id: str | None = None
    root_id: str | None = None

    def __post_init__(self) -> None:
        if self.root_id is None:
            object.__setattr__(self, "root_id", self.id)


@dataclass(frozen=True)
class Indefinite:
    """Represent an indefinite."""

    pass


@dataclass(frozen=True)
class UntilTurnStart:
    """Represent an until turn start."""

    creature_ref: str
    round_number: int | None = None


@dataclass(frozen=True)
class UntilTurnEnd:
    """Represent an until turn end."""

    creature_ref: str
    round_number: int | None = None


@dataclass(frozen=True)
class Rounds:
    """Represent a rounds."""

    count: int

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("Effect duration must last at least one round.")


@dataclass(frozen=True)
class WhileParentExists:
    """Represent a while parent exists."""

    pass


type EffectDuration = (
    Indefinite | UntilTurnStart | UntilTurnEnd | Rounds | WhileParentExists
)


class OngoingEffectKind(StrEnum):
    """Enumerate supported ongoing effect kind values."""

    GENERIC = "generic"
    CONCENTRATION = "concentration"
    CURSE = "curse"
    TEMPORARY_IMMUNITY = "temporary_immunity"
    SPELL = "spell"


class EffectPolarity(StrEnum):
    """Enumerate supported effect polarity values."""

    BENEFICIAL = "beneficial"
    HARMFUL = "harmful"
    NEUTRAL = "neutral"


class EffectTag(StrEnum):
    """Enumerate supported effect tag values."""

    CURSE = "curse"
    DISPELLABLE = "dispellable"


@dataclass(frozen=True)
class OngoingEffect:
    """Represent an ongoing effect."""

    identity: RuntimeStateIdentity
    target_refs: tuple[str, ...]
    duration: EffectDuration = field(default_factory=Indefinite)
    kind: OngoingEffectKind = OngoingEffectKind.GENERIC
    polarity: EffectPolarity = EffectPolarity.NEUTRAL
    parameters: dict[str, object] = field(default_factory=dict)
    dispellable: bool = False
    tags: frozenset[EffectTag] = frozenset()
    rule_effects: tuple[RuntimeRuleEffect, ...] = ()


class RelationshipKind(StrEnum):
    """Enumerate supported relationship kind values."""

    GRAPPLING = "grappling"
    SWALLOWED = "swallowed"


@dataclass(frozen=True)
class CreatureRelationship:
    """Represent a creature relationship."""

    identity: RuntimeStateIdentity
    kind: RelationshipKind
    source_ref: str
    target_ref: str
    duration: EffectDuration = field(default_factory=Indefinite)
    metadata: dict[str, object] = field(default_factory=dict)
