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
