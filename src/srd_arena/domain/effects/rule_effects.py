"""Typed rule contributions carried by ongoing effects.

These values describe how an effect can answer combat-rule queries. They do
not apply themselves to a creature; encounter rules decide how contributions
compose for a particular question.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

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
    """Limit how many attacks one Attack action can make."""

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


type RuntimeRuleEffect = (
    ArmorClassAdjustment
    | SpeedAdjustment
    | SpeedMultiplier
    | RollAdjustment
    | ReactionProhibition
    | ActionEconomyRestriction
    | AttackLimit
    | InvocationFailureChance
)


def serialize_runtime_rule_effect(
    effect: RuntimeRuleEffect,
) -> dict[str, object]:
    """Serialize one typed contribution for events and state inspection.

    >>> serialize_runtime_rule_effect(ArmorClassAdjustment(2))
    {'type': 'armor_class_adjustment', 'value': 2}
    """

    if isinstance(effect, ArmorClassAdjustment):
        return {"type": "armor_class_adjustment", "value": effect.value}
    if isinstance(effect, SpeedAdjustment):
        return {"type": "speed_adjustment", "feet": effect.feet}
    if isinstance(effect, SpeedMultiplier):
        return {
            "type": "speed_multiplier",
            "numerator": effect.numerator,
            "denominator": effect.denominator,
        }
    if isinstance(effect, RollAdjustment):
        modifier = effect.modifier
        return {
            "type": "roll_adjustment",
            "roll": modifier.roll,
            "mode": modifier.mode,
            "dice": modifier.dice,
            "value": modifier.value,
            "subject": modifier.subject,
            "ignored_by_senses": list(modifier.ignored_by_senses),
            "ability": modifier.ability,
        }
    if isinstance(effect, ReactionProhibition):
        return {
            "type": "reaction_prohibition",
            "reaction_kinds": sorted(effect.reaction_kinds),
        }
    if isinstance(effect, ActionEconomyRestriction):
        return {
            "type": "action_economy_restriction",
            "choose_between": sorted(kind.value for kind in effect.choose_between),
        }
    if isinstance(effect, AttackLimit):
        return {"type": "attack_limit", "maximum": effect.maximum}
    if isinstance(effect, InvocationFailureChance):
        return {
            "type": "invocation_failure_chance",
            "invocation_kinds": sorted(effect.invocation_kinds),
            "required_components": sorted(effect.required_components),
            "numerator": effect.numerator,
            "denominator": effect.denominator,
            "code": effect.code,
            "message": effect.message,
        }
    raise TypeError(f"Unsupported runtime rule effect: {effect!r}")
