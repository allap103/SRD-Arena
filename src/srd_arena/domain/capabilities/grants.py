from dataclasses import dataclass
from typing import Literal

from .definitions import CapabilityDefinition


@dataclass(frozen=True)
class LimitedUsePool:
    id: str
    maximum: int
    refresh: Literal["short_rest", "long_rest", "day"]
    kind: Literal["limited_uses"] = "limited_uses"


@dataclass(frozen=True)
class RechargePool:
    id: str
    die_sides: int
    minimum: int
    kind: Literal["recharge"] = "recharge"


@dataclass(frozen=True)
class SpellSlotPool:
    id: str
    maximum_by_level: tuple[tuple[int, int], ...]
    refresh: Literal["short_rest", "long_rest"] = "long_rest"
    kind: Literal["spell_slots"] = "spell_slots"


ResourcePoolDefinition = LimitedUsePool | RechargePool | SpellSlotPool


@dataclass(frozen=True)
class PoolUseCost:
    pool_id: str
    amount: int = 1
    kind: Literal["pool_use"] = "pool_use"


@dataclass(frozen=True)
class SpellSlotCost:
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
    id: str
    definition: CapabilityDefinition
    activation: CapabilityActivation
    cost: ResourceCost | None = None
