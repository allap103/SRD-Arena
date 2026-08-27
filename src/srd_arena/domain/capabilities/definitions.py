"""Composition models for complete executable capability definitions."""

from dataclasses import dataclass
from typing import Literal

from .requirements import CapabilityRequirement
from .resolutions import (
    AttackBonus,
    AttackResolution,
    AutomaticResolution,
    CapabilityResolution,
    DerivedAttackBonus,
    DerivedDifficultyClass,
    DifficultyClass,
    FixedAttackBonus,
    FixedDifficultyClass,
    Outcome,
    SavingThrowResolution,
)
from .scaling import (
    CapabilityScaling,
    ScalingIncrement,
    ScalingThreshold,
)
from .targeting import CapabilityTarget


@dataclass(frozen=True)
class CapabilityTrigger:
    """Represent a capability trigger."""

    event: str
    resolution: CapabilityResolution
    requirements: tuple[CapabilityRequirement, ...] = ()


@dataclass(frozen=True)
class CapabilityStep:
    """Represent a capability step."""

    target: CapabilityTarget
    resolution: CapabilityResolution


@dataclass(frozen=True)
class CapabilityRepetition:
    """Represent a capability repetition."""

    count: int | Literal["ability_modifier", "resource_scaled"]
    allocation: Literal[
        "same_target", "same_or_different", "different_targets", "propagating"
    ] = "same_or_different"
    simultaneous: bool = False
    propagation_range_feet: int | None = None
    cannot_repeat_target: bool = False


@dataclass(frozen=True)
class CapabilityDefinition:
    """Represent a capability definition."""

    target: CapabilityTarget
    resolution: CapabilityResolution
    condition_selection: Literal["all", "choose_one"] = "all"
    repetition: CapabilityRepetition | None = None
    scaling: tuple[CapabilityScaling, ...] = ()
    triggers: tuple[CapabilityTrigger, ...] = ()
    follow_ups: tuple[CapabilityStep, ...] = ()


# Preserve the former definitions-module import surface while the models live in
# modules named after their responsibility.
__all__ = [
    "AttackBonus",
    "AttackResolution",
    "AutomaticResolution",
    "CapabilityDefinition",
    "CapabilityRepetition",
    "CapabilityResolution",
    "CapabilityScaling",
    "CapabilityStep",
    "CapabilityTrigger",
    "DerivedAttackBonus",
    "DerivedDifficultyClass",
    "DifficultyClass",
    "FixedAttackBonus",
    "FixedDifficultyClass",
    "Outcome",
    "SavingThrowResolution",
    "ScalingIncrement",
    "ScalingThreshold",
]
