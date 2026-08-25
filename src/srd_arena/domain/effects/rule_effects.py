"""Typed rule contributions carried by ongoing effects.

These values describe how an effect can answer combat-rule queries. They do
not apply themselves to a creature; encounter rules decide how contributions
compose for a particular question.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from .modifiers import RollModifier


class ActionEconomyKind(StrEnum):
    """A turn resource that may be restricted relative to another one."""

    ACTION = "action"
    BONUS_ACTION = "bonus_action"


@dataclass(frozen=True)
class ArmorClassAdjustment:
    """Add ``value`` to a creature's effective Armor Class."""

    value: int


@dataclass(frozen=True)
class SpeedAdjustment:
    """Add ``feet`` to a creature's effective Speed."""

    feet: int


@dataclass(frozen=True)
class SpeedMultiplier:
    """Multiply a creature's effective Speed by a non-negative fraction."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if self.numerator < 0:
            raise ValueError("Speed multiplier numerator cannot be negative.")
        if self.denominator <= 0:
            raise ValueError("Speed multiplier denominator must be positive.")


@dataclass(frozen=True)
class RollAdjustment:
    """Contribute one existing roll modifier to a rule query."""

    modifier: RollModifier


@dataclass(frozen=True)
class ReactionProhibition:
    """Prohibit all reactions, or only the named reaction kinds."""

    reaction_kinds: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ActionEconomyRestriction:
    """Require a turn to choose between the listed action-economy kinds."""

    choose_between: frozenset[ActionEconomyKind]

    def __post_init__(self) -> None:
        if len(self.choose_between) < 2:
            raise ValueError(
                "Action economy restriction must contain at least two choices."
            )


@dataclass(frozen=True)
class AttackLimit:
    """Limit how many attacks an action can make."""

    maximum: int

    def __post_init__(self) -> None:
        if self.maximum < 1:
            raise ValueError("Attack limit must be positive.")


@dataclass(frozen=True)
class InvocationFailureChance:
    """Give qualifying invocations a fractional chance to fail at start."""

    invocation_kinds: frozenset[str]
    required_components: frozenset[str]
    numerator: int
    denominator: int
    code: str
    message: str

    def __post_init__(self) -> None:
        if not self.invocation_kinds:
            raise ValueError("Invocation failure chance requires an invocation kind.")
        if self.denominator <= 0:
            raise ValueError("Invocation failure denominator must be positive.")
        if not 0 <= self.numerator <= self.denominator:
            raise ValueError(
                "Invocation failure numerator must be between zero and denominator."
            )
        if not self.code.strip():
            raise ValueError("Invocation failure chance requires a code.")
        if not self.message.strip():
            raise ValueError("Invocation failure chance requires a message.")


RuntimeRuleEffect: TypeAlias = (
    ArmorClassAdjustment
    | SpeedAdjustment
    | SpeedMultiplier
    | RollAdjustment
    | ReactionProhibition
    | ActionEconomyRestriction
    | AttackLimit
    | InvocationFailureChance
)
