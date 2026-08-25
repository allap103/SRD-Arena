"""Level-dependent changes to capability definitions."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ScalingIncrement:
    kind: Literal[
        "damage_dice",
        "healing_dice",
        "healing_bonus",
        "temporary_hit_points",
        "hit_point_maximum",
        "target_count",
        "projectile_count",
        "area_radius_feet",
        "duration",
    ]
    amount: int | str
    damage_type: str | None = None


@dataclass(frozen=True)
class ScalingThreshold:
    minimum_level: int
    increments: tuple[ScalingIncrement, ...]


@dataclass(frozen=True)
class CapabilityScaling:
    basis: Literal["resource_level", "actor_level"]
    above_level: int | Literal["base_level"] = "base_level"
    per_level: tuple[ScalingIncrement, ...] = ()
    thresholds: tuple[ScalingThreshold, ...] = ()
