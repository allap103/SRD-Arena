"""State changes produced by capability resolution."""

from dataclasses import dataclass
from typing import Literal

from .requirements import CapabilityRequirement, CreatureTypeRequirement


@dataclass(frozen=True)
class EffectDuration:
    kind: str
    amount: int | None = None
    unit: str | None = None
    creature: str | None = None
    turn_offset: int = 0
    events: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttackRollModeRequirement:
    mode: Literal["normal", "advantage", "disadvantage"]


AttackHitRequirement = AttackRollModeRequirement


@dataclass(frozen=True)
class DamageEffect:
    dice: str
    bonus: int
    damage_type: str
    minimum: int | None = None
    requirements: tuple[AttackHitRequirement, ...] = ()


@dataclass(frozen=True)
class HealingEffect:
    dice: str | None = None
    bonus: int = 0
    modifier: Literal["none", "ability_modifier"] = "none"
    from_damage: Literal["none", "half_damage_dealt", "all_damage_dealt"] = "none"
    restore_to_maximum: bool = False
    pool: int | None = None


@dataclass(frozen=True)
class TemporaryHitPointsEffect:
    dice: str | None = None
    value: int = 0
    modifier: Literal["none", "ability_modifier"] = "none"
    trigger: Literal["application", "target_turn_start"] = "application"


@dataclass(frozen=True)
class ArmorClassModifierEffect:
    value: int
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class RemoveEffect:
    removable: tuple[str, ...]
    selection: Literal["one", "all"] = "one"
    conditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DamageResistanceEffect:
    damage_types: tuple[str, ...]
    selection: Literal["all", "choose_one"] = "all"
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class DamageReductionEffect:
    damage_types: tuple[str, ...]
    dice: str
    selection: Literal["all", "choose_one"] = "all"
    limit: int = 1
    period: Literal["turn"] = "turn"
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class SpeedModifierEffect:
    feet: int
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class ConditionSaveAdvantageEffect:
    conditions: tuple[str, ...]
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class DamageImmunityEffect:
    damage_types: tuple[str, ...]
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class ConditionImmunityEffect:
    conditions: tuple[str, ...]
    suppress_existing: bool = False
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class SenseEffect:
    sense: Literal["blindsight", "darkvision", "truesight"]
    range_feet: int
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class HitPointMaximumModifierEffect:
    value: int
    also_modify_current: bool = False
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class ConditionEffect:
    condition: str
    duration: EffectDuration | None = None
    requirements: tuple[CapabilityRequirement, ...] = ()
    escape_dc: int | None = None
    source_capacity: int | None = None
    ends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class ForcedMovementEffect:
    direction: str
    distance_feet: int
    up_to: bool


@dataclass(frozen=True)
class SpeedMultiplierEffect:
    numerator: int
    denominator: int
    duration: EffectDuration


@dataclass(frozen=True)
class ProhibitReactionsEffect:
    duration: EffectDuration


@dataclass(frozen=True)
class TurnEconomyRestrictionEffect:
    choose_between: tuple[str, ...]
    duration: EffectDuration


@dataclass(frozen=True)
class RollModifierEffect:
    roll: str
    mode: str
    ability: str | None = None
    dice: str | None = None
    value: int | None = None
    duration: EffectDuration | None = None
    ability_options: tuple[str, ...] = ()
    subject: Literal["target", "attacks_against_target"] = "target"
    ignored_by_senses: tuple[str, ...] = ()
    requirements: tuple[CapabilityRequirement, ...] = ()


@dataclass(frozen=True)
class ControlEffect:
    communication: str | None
    communication_range_feet: int | Literal["unlimited"] | None
    control_range_feet: int | None
    duration: EffectDuration


@dataclass(frozen=True)
class GainMemoriesEffect:
    requirement: CreatureTypeRequirement
    trigger: str


CapabilityEffect = (
    DamageEffect
    | HealingEffect
    | TemporaryHitPointsEffect
    | ArmorClassModifierEffect
    | RemoveEffect
    | DamageResistanceEffect
    | DamageReductionEffect
    | SpeedModifierEffect
    | ConditionSaveAdvantageEffect
    | DamageImmunityEffect
    | ConditionImmunityEffect
    | SenseEffect
    | HitPointMaximumModifierEffect
    | ConditionEffect
    | ForcedMovementEffect
    | SpeedMultiplierEffect
    | ProhibitReactionsEffect
    | TurnEconomyRestrictionEffect
    | RollModifierEffect
    | ControlEffect
    | GainMemoriesEffect
)
