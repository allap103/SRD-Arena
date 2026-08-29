"""Model sourced, durable effect state owned by a running encounter."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from .rule_effects import RuntimeRuleEffect

if TYPE_CHECKING:
    from .conditions import Condition


class EffectSourceKind(StrEnum):
    """Classify the rules object responsible for creating runtime state."""

    CREATURE = "creature"
    ACTION = "action"
    SPELL = "spell"
    FEATURE = "feature"
    ITEM = "item"
    ENVIRONMENT = "environment"
    SYSTEM = "system"


@dataclass(frozen=True)
class EffectSource:
    """Identify the definition, applier, and occurrence that produced state.

    ``definition_id`` names reusable rules content, while ``origin_id``
    distinguishes one runtime occurrence of that content.
    """

    kind: EffectSourceKind
    definition_id: str
    applied_by_ref: str | None = None
    label: str | None = None
    origin_id: str = ""


@dataclass(frozen=True)
class RuntimeStateIdentity:
    """Give runtime state a stable ID and optional effect-tree ancestry.

    Parent and root identities allow a single spell or action occurrence to
    own several conditions, relationships, and ongoing effects that can later
    be removed together.
    """

    id: str
    source: EffectSource
    parent_id: str | None = None
    root_id: str | None = None

    def __post_init__(self) -> None:
        if self.root_id is None:
            object.__setattr__(self, "root_id", self.id)


@dataclass(frozen=True)
class Indefinite:
    """Mark state that persists until an explicit rule removes it."""

    pass


@dataclass(frozen=True)
class UntilTurnStart:
    """Expire state when the named creature reaches the configured turn start."""

    creature_ref: str
    round_number: int | None = None


@dataclass(frozen=True)
class UntilTurnEnd:
    """Expire state when the named creature reaches the configured turn end."""

    creature_ref: str
    round_number: int | None = None


@dataclass(frozen=True)
class Rounds:
    """Keep state for a positive number of encounter rounds."""

    count: int

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("Effect duration must last at least one round.")


@dataclass(frozen=True)
class WhileParentExists:
    """Keep child state only while its parent runtime state exists."""

    pass


type EffectDuration = (
    Indefinite | UntilTurnStart | UntilTurnEnd | Rounds | WhileParentExists
)


class OngoingEffectKind(StrEnum):
    """Classify durable non-condition state for lifecycle operations."""

    GENERIC = "generic"
    CONCENTRATION = "concentration"
    CURSE = "curse"
    TEMPORARY_IMMUNITY = "temporary_immunity"
    SPELL = "spell"


class EffectPolarity(StrEnum):
    """Describe whether an effect benefits, harms, or neutrally affects a target."""

    BENEFICIAL = "beneficial"
    HARMFUL = "harmful"
    NEUTRAL = "neutral"


class EffectTag(StrEnum):
    """Mark cross-cutting properties used to find or remove ongoing effects."""

    CURSE = "curse"
    DISPELLABLE = "dispellable"


@dataclass(frozen=True)
class RepeatedDamage:
    """Describe damage dealt after a failed repeat save."""

    dice: str
    damage_type: str


@dataclass(frozen=True)
class RepeatSaveLifecycle:
    """Describe a recurring save and the consequences of failure."""

    trigger: str
    ability: str
    dc: int
    failure_conditions: tuple[Condition, ...] = ()
    failure_damage: tuple[RepeatedDamage, ...] = ()
    damage_grants_advantage: bool = False
    progressed_target_refs: frozenset[str] = frozenset()


@dataclass(frozen=True)
class EndEventRule:
    """End an effect when a named event occurs within the configured scope."""

    event: str
    scope: str


@dataclass(frozen=True)
class OngoingEffectLifecycle:
    """Hold typed turn, event, and duration-progress behavior for an effect."""

    started_round: int | None = None
    repeat_save: RepeatSaveLifecycle | None = None
    end_events: tuple[EndEventRule, ...] = ()
    turn_start_temporary_hit_points: int = 0


@dataclass(frozen=True)
class OngoingEffect:
    """Track sourced non-condition state that persists across rule events.

    Ongoing effects cover concentration, curses, spell-specific state, and
    other mechanics whose lifecycle or rule contributions cannot be expressed
    as a condition alone. Encounter rule queries interpret ``rule_effects``;
    this value does not modify creatures by itself.
    """

    identity: RuntimeStateIdentity
    target_refs: tuple[str, ...]
    duration: EffectDuration = field(default_factory=Indefinite)
    kind: OngoingEffectKind = OngoingEffectKind.GENERIC
    polarity: EffectPolarity = EffectPolarity.NEUTRAL
    label: str | None = None
    lifecycle: OngoingEffectLifecycle = field(default_factory=OngoingEffectLifecycle)
    dispellable: bool = False
    tags: frozenset[EffectTag] = frozenset()
    rule_effects: tuple[RuntimeRuleEffect, ...] = ()


class RelationshipKind(StrEnum):
    """Name directional relationships maintained between encounter creatures."""

    GRAPPLING = "grappling"
    SWALLOWED = "swallowed"


@dataclass(frozen=True)
class CreatureRelationship:
    """Track one sourced, directional relationship between two creatures.

    Relationships record facts such as who is grappling whom. They remain
    separate from target-side conditions because their source and target have
    different rule responsibilities.
    """

    identity: RuntimeStateIdentity
    kind: RelationshipKind
    source_ref: str
    target_ref: str
    duration: EffectDuration = field(default_factory=Indefinite)
    metadata: dict[str, object] = field(default_factory=dict)
