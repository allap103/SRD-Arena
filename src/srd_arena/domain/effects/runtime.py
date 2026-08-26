from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias

from .rule_effects import RuntimeRuleEffect


class EffectSourceKind(StrEnum):
    CREATURE = "creature"
    ACTION = "action"
    SPELL = "spell"
    FEATURE = "feature"
    ITEM = "item"
    ENVIRONMENT = "environment"
    SYSTEM = "system"


@dataclass(frozen=True)
class EffectSource:
    kind: EffectSourceKind
    definition_id: str
    applied_by_ref: str | None = None
    label: str | None = None
    origin_id: str = ""


@dataclass(frozen=True)
class RuntimeStateIdentity:
    id: str
    source: EffectSource
    parent_id: str | None = None
    root_id: str | None = None

    def __post_init__(self) -> None:
        if self.root_id is None:
            object.__setattr__(self, "root_id", self.id)


@dataclass(frozen=True)
class Indefinite:
    pass


@dataclass(frozen=True)
class UntilTurnStart:
    creature_ref: str
    round_number: int | None = None


@dataclass(frozen=True)
class UntilTurnEnd:
    creature_ref: str
    round_number: int | None = None


@dataclass(frozen=True)
class Rounds:
    count: int

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("Effect duration must last at least one round.")


@dataclass(frozen=True)
class WhileParentExists:
    pass


EffectDuration: TypeAlias = (
    Indefinite | UntilTurnStart | UntilTurnEnd | Rounds | WhileParentExists
)


class OngoingEffectKind(StrEnum):
    GENERIC = "generic"
    CONCENTRATION = "concentration"
    CURSE = "curse"
    TEMPORARY_IMMUNITY = "temporary_immunity"
    SPELL = "spell"


class EffectPolarity(StrEnum):
    BENEFICIAL = "beneficial"
    HARMFUL = "harmful"
    NEUTRAL = "neutral"


class EffectTag(StrEnum):
    CURSE = "curse"
    DISPELLABLE = "dispellable"


@dataclass(frozen=True)
class OngoingEffect:
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
    GRAPPLING = "grappling"
    SWALLOWED = "swallowed"


@dataclass(frozen=True)
class CreatureRelationship:
    identity: RuntimeStateIdentity
    kind: RelationshipKind
    source_ref: str
    target_ref: str
    duration: EffectDuration = field(default_factory=Indefinite)
    metadata: dict[str, object] = field(default_factory=dict)
