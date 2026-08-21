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
class CapabilityDefinition:
    target: CapabilityTarget
    resolution: CapabilityResolution
