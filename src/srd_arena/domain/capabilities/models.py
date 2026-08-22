from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SizeRequirement:
    maximum: str | None = None
    minimum: str | None = None


@dataclass(frozen=True)
class ConditionRequirement:
    conditions: tuple[str, ...]
    match: Literal["any", "all"] = "any"
    applied_by: Literal["source", "any"] = "any"


@dataclass(frozen=True)
class CreatureTypeRequirement:
    creature_types: tuple[str, ...]


@dataclass(frozen=True)
class NotAffectedRequirement:
    action: str


CapabilityRequirement = (
    SizeRequirement
    | ConditionRequirement
    | CreatureTypeRequirement
    | NotAffectedRequirement
)


@dataclass(frozen=True)
class TargetCount:
    minimum: int = 1
    maximum: int | Literal["all", "ability_modifier"] = 1


@dataclass(frozen=True)
class CapabilityTarget:
    kind: Literal["self", "creature", "area"]
    count: TargetCount = TargetCount()
    range_feet: int | None = None
    shape: str | None = None
    size_feet: int | None = None
    width_feet: int | None = None
    origin: str = "self"
    line_of_sight: bool = False
    disposition: Literal[
        "any", "ally", "enemy", "willing", "source", "trigger_target"
    ] = "any"
    selection: Literal["all", "choose", "choose_up_to"] = "choose"
    occupants: Literal["all", "allies", "enemies", "chosen"] = "all"
    excludes_source: bool = False
    requirements: tuple[CapabilityRequirement, ...] = ()


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
    | ConditionEffect
    | ForcedMovementEffect
    | SpeedMultiplierEffect
    | ProhibitReactionsEffect
    | TurnEconomyRestrictionEffect
    | RollModifierEffect
    | ControlEffect
    | GainMemoriesEffect
)


@dataclass(frozen=True)
class RepeatSave:
    trigger: str
    interval_amount: int | None = None
    interval_unit: str | None = None
    distance_from_source_feet: int | None = None
    effects_end_on_success: bool = True
    automatic_success_after: EffectDuration | None = None


@dataclass(frozen=True)
class OutcomeStage:
    effects: tuple[CapabilityEffect, ...]
    repeat_saves: tuple[RepeatSave, ...] = ()
