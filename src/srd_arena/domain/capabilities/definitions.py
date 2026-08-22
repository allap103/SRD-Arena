from dataclasses import dataclass
from typing import Literal

from .models import CapabilityEffect, OutcomeStage, CapabilityTarget


@dataclass(frozen=True)
class Outcome:
    effects: tuple[CapabilityEffect, ...] = ()


@dataclass(frozen=True)
class AutomaticResolution:
    outcome: Outcome
    kind: Literal["automatic"] = "automatic"


@dataclass(frozen=True)
class FixedAttackBonus:
    value: int
    kind: Literal["fixed"] = "fixed"


@dataclass(frozen=True)
class DerivedAttackBonus:
    derivation: Literal["spell_attack_modifier"]
    kind: Literal["derived"] = "derived"


AttackBonus = FixedAttackBonus | DerivedAttackBonus


@dataclass(frozen=True)
class AttackResolution:
    modes: tuple[Literal["melee", "ranged"], ...]
    attack_bonus: AttackBonus
    hit: Outcome
    miss: Outcome = Outcome()
    attacks: int = 1
    allocation: Literal["same_target", "same_or_different"] = "same_target"
    kind: Literal["attack"] = "attack"


@dataclass(frozen=True)
class FixedDifficultyClass:
    value: int
    kind: Literal["fixed"] = "fixed"


@dataclass(frozen=True)
class DerivedDifficultyClass:
    derivation: Literal["spell_save_dc", "ten_plus_spell_level"]
    kind: Literal["derived"] = "derived"


DifficultyClass = FixedDifficultyClass | DerivedDifficultyClass


@dataclass(frozen=True)
class SavingThrowResolution:
    ability: str
    difficulty: DifficultyClass
    failure: tuple[OutcomeStage, ...]
    success: Outcome = Outcome()
    always: Outcome = Outcome()
    success_damage: Literal["none", "half"] = "none"
    kind: Literal["saving_throw"] = "saving_throw"


CapabilityResolution = (
    AttackResolution | AutomaticResolution | SavingThrowResolution
)


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


@dataclass(frozen=True)
class CapabilityRepetition:
    count: int | Literal["ability_modifier", "resource_scaled"]
    allocation: Literal[
        "same_target", "same_or_different", "different_targets", "propagating"
    ] = "same_or_different"
    simultaneous: bool = False
    propagation_range_feet: int | None = None
    cannot_repeat_target: bool = False


@dataclass(frozen=True)
class CapabilityDefinition:
    target: CapabilityTarget
    resolution: CapabilityResolution
    repetition: CapabilityRepetition | None = None
    scaling: tuple[CapabilityScaling, ...] = ()
