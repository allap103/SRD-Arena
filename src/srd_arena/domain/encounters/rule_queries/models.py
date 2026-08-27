"""Typed results returned by encounter rule queries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from math import floor

from ...effects.modifiers import RollModifier
from ...effects.runtime import EffectSource
from ...geometry import MovementBudget
from ...rolls.dice import D20RollMode, DieRoller, combine_roll_modes
from ..actions.eligibility_rules.models import EligibilityFailure
from ..models import CreatureRef


class NumericOperation(StrEnum):
    """A supported contribution to an integer-valued combat rule."""

    ADD = "add"
    MULTIPLY = "multiply"
    UPPER_CAP = "upper_cap"


@dataclass(frozen=True)
class NumericRuleContribution:
    """One sourced adjustment to a numeric rule value."""

    provider_state_id: str
    source: EffectSource
    operation: NumericOperation
    amount: int
    denominator: int = 1

    def __post_init__(self) -> None:
        if self.denominator < 1:
            raise ValueError("A numeric contribution denominator must be positive.")
        if self.operation is not NumericOperation.MULTIPLY and self.denominator != 1:
            raise ValueError("Only multiplication contributions use a denominator.")


@dataclass(frozen=True)
class NumericRuleResult:
    """A base value plus ordered groups of sourced numeric contributions."""

    base: int
    contributions: tuple[NumericRuleContribution, ...] = ()
    minimum: int | None = None

    @property
    def value(self) -> int:
        """Apply additions, then multipliers, then upper caps."""

        value = Fraction(
            self.base
            + sum(
                contribution.amount
                for contribution in self.contributions
                if contribution.operation is NumericOperation.ADD
            )
        )
        for contribution in self.contributions:
            if contribution.operation is NumericOperation.MULTIPLY:
                value *= Fraction(
                    contribution.amount,
                    contribution.denominator,
                )
        resolved = floor(value)
        caps = tuple(
            contribution.amount
            for contribution in self.contributions
            if contribution.operation is NumericOperation.UPPER_CAP
        )
        if caps:
            resolved = min(resolved, *caps)
        return max(self.minimum, resolved) if self.minimum is not None else resolved


@dataclass(frozen=True)
class MovementQueryResult:
    """Effective Speed and its grid-specific movement budget."""

    speed: NumericRuleResult
    budget: MovementBudget


@dataclass(frozen=True)
class RollRuleContribution:
    """One sourced modifier that applies to a requested roll."""

    provider_state_id: str
    source: EffectSource
    modifier: RollModifier


@dataclass(frozen=True)
class RollRuleResult:
    """All sourced modifiers applicable to one roll context."""

    contributions: tuple[RollRuleContribution, ...] = ()

    @property
    def mode(self) -> D20RollMode:
        return combine_roll_modes(
            *(
                mode
                for contribution in self.contributions
                if (mode := contribution.modifier.roll_mode) is not None
            )
        )

    def resolve_modifier(self, roller: DieRoller) -> int:
        return sum(
            contribution.modifier.resolve(roller) for contribution in self.contributions
        )


@dataclass(frozen=True)
class SourcedEligibilityFailure(EligibilityFailure):
    """An eligibility failure retaining the sources behind its state IDs."""

    sources: tuple[EffectSource, ...] = ()


@dataclass(frozen=True)
class InvocationStartContext:
    """Facts available before one invocation starts resolving."""

    actor_ref: CreatureRef
    kind: str
    components: frozenset[str] = frozenset()


@dataclass(frozen=True)
class InvocationFailureChanceContribution:
    """A sourced chance that prevents an invocation from starting."""

    provider_state_id: str
    source: EffectSource
    numerator: int
    denominator: int
    code: str
    message: str

    def __post_init__(self) -> None:
        if self.denominator < 1:
            raise ValueError("An invocation failure denominator must be positive.")
        if not 0 <= self.numerator <= self.denominator:
            raise ValueError("An invocation failure chance must be between 0 and 1.")


@dataclass(frozen=True)
class InvocationStartQueryResult:
    """The sourced failure checks that apply to one invocation."""

    context: InvocationStartContext
    failure_chances: tuple[InvocationFailureChanceContribution, ...] = ()


@dataclass(frozen=True)
class InvocationStartRoll:
    """The die result for one invocation-start failure chance."""

    contribution: InvocationFailureChanceContribution
    roll: int
    failed: bool

    @property
    def provider_state_id(self) -> str:
        return self.contribution.provider_state_id

    @property
    def source(self) -> EffectSource:
        return self.contribution.source

    @property
    def code(self) -> str:
        return self.contribution.code

    @property
    def message(self) -> str:
        return self.contribution.message


@dataclass(frozen=True)
class InvocationStartResult:
    """Resolved invocation-start checks, including every chance roll."""

    context: InvocationStartContext
    rolls: tuple[InvocationStartRoll, ...] = ()

    @property
    def allowed(self) -> bool:
        return not any(roll.failed for roll in self.rolls)

    @property
    def failures(self) -> tuple[InvocationStartRoll, ...]:
        return tuple(roll for roll in self.rolls if roll.failed)
