from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DeclaredStatBlockAction:
    name: str
    display_name: str
    description: str
    capability_type: str | None = None
    section: Literal["action", "bonus_action"] = "action"


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


ActionRequirement = (
    SizeRequirement
    | ConditionRequirement
    | CreatureTypeRequirement
    | NotAffectedRequirement
)


@dataclass(frozen=True)
class ActionTarget:
    kind: Literal["self", "creature", "area"]
    range_feet: int | None = None
    shape: str | None = None
    size_feet: int | None = None
    width_feet: int | None = None
    origin: str = "self"
    line_of_sight: bool = False
    requirements: tuple[ActionRequirement, ...] = ()


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
    requirements: tuple[ActionRequirement, ...] = ()
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


ActionEffect = (
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
class ActionOutcomeStage:
    effects: tuple[ActionEffect, ...]
    repeat_saves: tuple[RepeatSave, ...] = ()


@dataclass(frozen=True)
class ActionResource:
    kind: Literal["uses", "recharge"]
    maximum: int | None = None
    reset: str | None = None
    die: str | None = None
    minimum: int | None = None


@dataclass(frozen=True)
class AttackActionDefinition:
    name: str
    attack_modes: tuple[str, ...]
    attack_bonus: int
    target: ActionTarget
    reach_feet: int | None
    range_normal_feet: int | None
    range_long_feet: int | None
    hit: tuple[ActionEffect, ...]
    resource: ActionResource | None = None


@dataclass(frozen=True)
class SavingThrowActionDefinition:
    name: str
    target: ActionTarget
    ability: str
    dc: int
    failure: tuple[ActionOutcomeStage, ...]
    success: tuple[ActionEffect, ...]
    success_damage: Literal["none", "half"]
    always: tuple[ActionEffect, ...]
    resource: ActionResource | None = None


@dataclass(frozen=True)
class AutomaticActionDefinition:
    name: str
    target: ActionTarget
    effects: tuple[ActionEffect, ...]
    resource: ActionResource | None = None


@dataclass(frozen=True)
class SpellOption:
    name: str
    source: str | None = None
    cast_level: int | None = None
    uses: int | Literal["at_will"] | None = None


@dataclass(frozen=True)
class SpellcastingActionDefinition:
    name: str
    ability: str
    spells: tuple[SpellOption, ...]
    shared_resource: ActionResource | None = None


StatBlockActionDefinition = (
    AttackActionDefinition
    | SavingThrowActionDefinition
    | AutomaticActionDefinition
    | SpellcastingActionDefinition
)
