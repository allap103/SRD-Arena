"""Ways an invoked capability determines its outcome."""

from dataclasses import dataclass
from typing import Literal

from .effects import CapabilityEffect, RollModifierEffect
from .outcomes import OutcomeStage
from .requirements import CapabilityRequirement


@dataclass(frozen=True)
class Outcome:
    """Collect state-changing effects produced by one resolution branch."""

    effects: tuple[CapabilityEffect, ...] = ()
    end_capability: bool = False


@dataclass(frozen=True)
class AutomaticResolution:
    """Apply an outcome without an attack roll or saving throw."""

    outcome: Outcome
    kind: Literal["automatic"] = "automatic"


@dataclass(frozen=True)
class FixedAttackBonus:
    """Use an explicitly authored modifier for a capability attack roll."""

    value: int
    kind: Literal["fixed"] = "fixed"


@dataclass(frozen=True)
class DerivedAttackBonus:
    """Derive an attack modifier from the invocation's actor context."""

    derivation: Literal["spell_attack_modifier"]
    kind: Literal["derived"] = "derived"


AttackBonus = FixedAttackBonus | DerivedAttackBonus


@dataclass(frozen=True)
class AttackResolution:
    """Resolve one or more attack rolls into hit and miss outcomes."""

    modes: tuple[Literal["melee", "ranged"], ...]
    attack_bonus: AttackBonus
    hit: Outcome
    miss: Outcome = Outcome()
    attacks: int = 1
    allocation: Literal["same_target", "same_or_different"] = "same_target"
    kind: Literal["attack"] = "attack"


@dataclass(frozen=True)
class FixedDifficultyClass:
    """Use an explicitly authored Difficulty Class for a saving throw."""

    value: int
    kind: Literal["fixed"] = "fixed"


@dataclass(frozen=True)
class DerivedDifficultyClass:
    """Derive a Difficulty Class from spell or invocation context."""

    derivation: Literal["spell_save_dc", "ten_plus_spell_level"]
    kind: Literal["derived"] = "derived"


DifficultyClass = FixedDifficultyClass | DerivedDifficultyClass


@dataclass(frozen=True)
class SavingThrowResolution:
    """Resolve a save into staged failure, success, and unconditional outcomes.

    Staged failures support effects that progress across repeated saves, while
    ``always`` captures mechanics applied regardless of the initial result.
    """

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
