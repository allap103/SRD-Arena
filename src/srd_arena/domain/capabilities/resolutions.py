"""Ways an invoked capability determines its outcome."""

from dataclasses import dataclass
from typing import Literal

from .effects import CapabilityEffect, RollModifierEffect
from .outcomes import OutcomeStage
from .requirements import CapabilityRequirement


@dataclass(frozen=True)
class Outcome:
    """Represent an outcome."""

    effects: tuple[CapabilityEffect, ...] = ()
    end_capability: bool = False


@dataclass(frozen=True)
class AutomaticResolution:
    """Represent an automatic resolution."""

    outcome: Outcome
    kind: Literal["automatic"] = "automatic"


@dataclass(frozen=True)
class FixedAttackBonus:
    """Represent a fixed attack bonus."""

    value: int
    kind: Literal["fixed"] = "fixed"


@dataclass(frozen=True)
class DerivedAttackBonus:
    """Represent a derived attack bonus."""

    derivation: Literal["spell_attack_modifier"]
    kind: Literal["derived"] = "derived"


AttackBonus = FixedAttackBonus | DerivedAttackBonus


@dataclass(frozen=True)
class AttackResolution:
    """Represent an attack resolution."""

    modes: tuple[Literal["melee", "ranged"], ...]
    attack_bonus: AttackBonus
    hit: Outcome
    miss: Outcome = Outcome()
    attacks: int = 1
    allocation: Literal["same_target", "same_or_different"] = "same_target"
    kind: Literal["attack"] = "attack"


@dataclass(frozen=True)
class FixedDifficultyClass:
    """Represent a fixed difficulty class."""

    value: int
    kind: Literal["fixed"] = "fixed"


@dataclass(frozen=True)
class DerivedDifficultyClass:
    """Represent a derived difficulty class."""

    derivation: Literal["spell_save_dc", "ten_plus_spell_level"]
    kind: Literal["derived"] = "derived"


DifficultyClass = FixedDifficultyClass | DerivedDifficultyClass


@dataclass(frozen=True)
class SavingThrowResolution:
    """Represent a saving throw resolution."""

    ability: str
    difficulty: DifficultyClass
    failure: tuple[OutcomeStage, ...]
    success: Outcome = Outcome()
    always: Outcome = Outcome()
    success_damage: Literal["none", "half"] = "none"
    automatic_success: tuple[CapabilityRequirement, ...] = ()
    automatic_failure: tuple[CapabilityRequirement, ...] = ()
    save_modifiers: tuple[RollModifierEffect, ...] = ()
    kind: Literal["saving_throw"] = "saving_throw"


CapabilityResolution = AttackResolution | AutomaticResolution | SavingThrowResolution
