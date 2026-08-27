"""Bind reusable capabilities to activation and resource-consumption rules."""

from dataclasses import dataclass
from typing import Literal

from .definitions import CapabilityDefinition


@dataclass(frozen=True)
class LimitedUsePool:
    """Define a fixed number of uses restored at a named refresh boundary."""

    id: str
    maximum: int
    refresh: Literal["short_rest", "long_rest", "day"]
    kind: Literal["limited_uses"] = "limited_uses"


@dataclass(frozen=True)
class RechargePool:
    """Define availability restored by meeting a threshold on a recharge roll."""

    id: str
    die_sides: int
    minimum: int
    kind: Literal["recharge"] = "recharge"


@dataclass(frozen=True)
class SpellSlotPool:
    """Define level-indexed spell-slot capacities sharing one refresh rule."""

    id: str
    maximum_by_level: tuple[tuple[int, int], ...]
    refresh: Literal["short_rest", "long_rest"] = "long_rest"
    kind: Literal["spell_slots"] = "spell_slots"


ResourcePoolDefinition = LimitedUsePool | RechargePool | SpellSlotPool


@dataclass(frozen=True)
class PoolUseCost:
    """Spend a fixed amount from a referenced limited-use resource pool."""

    pool_id: str
    amount: int = 1
    kind: Literal["pool_use"] = "pool_use"


@dataclass(frozen=True)
class SpellSlotCost:
    """Spend a spell slot at or above the capability's minimum level."""

    pool_id: str
    minimum_level: int
    allow_higher_level: bool = True
    kind: Literal["spell_slot"] = "spell_slot"


ResourceCost = PoolUseCost | SpellSlotCost
CapabilityActivation = Literal[
    "action",
    "bonus_action",
    "reaction",
    "free_action",
    "passive",
]


@dataclass(frozen=True)
class CapabilityGrant:
    """Expose a capability through one activation and optional resource cost.

    The definition contains reusable mechanics; the grant describes how a
    particular creature-facing option invokes and pays for those mechanics.
    """

    id: str
    definition: CapabilityDefinition
    activation: CapabilityActivation
    cost: ResourceCost | None = None
