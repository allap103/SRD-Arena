"""State changes produced by capability resolution."""

from dataclasses import dataclass
from typing import Literal

from .requirements import CapabilityRequirement, CreatureTypeRequirement


@dataclass(frozen=True)
class EffectDuration:
    """Declare when state created by a capability effect should expire."""

    kind: str
    amount: int | None = None
    unit: str | None = None
    creature: str | None = None
    turn_offset: int = 0
    events: tuple[str, ...] = ()
    event_match: Literal["any", "all"] = "any"


@dataclass(frozen=True)
class AttackRollModeRequirement:
    """Apply an effect only when its attack used the required roll mode."""

    mode: Literal["normal", "advantage", "disadvantage"]


AttackHitRequirement = AttackRollModeRequirement


@dataclass(frozen=True)
class DamageEffect:
    """Deal typed dice damage when the containing outcome resolves."""

    dice: str
    bonus: int
    damage_type: str
    minimum: int | None = None
    requirements: tuple[AttackHitRequirement, ...] = ()


@dataclass(frozen=True)
class HitPointMaximumReductionEffect:
    """Reduce maximum HP by damage actually applied during this outcome."""

    amount: Literal["damage_taken"]


@dataclass(frozen=True)
class AttackHitDamageEffect:
    """Add typed dice damage when the effect source hits its marked target."""

    dice: str
    damage_type: str


@dataclass(frozen=True)
class AttackHitRetaliationEffect:
    """Damage an attacker after it hits the protected target with an attack."""

    value: int
    damage_type: str
    attack_types: tuple[Literal["melee", "ranged"], ...]
    requires_temporary_hit_points: bool = False
    end_effect_when_depleted: bool = False


@dataclass(frozen=True)
class HealingEffect:
    """Restore Hit Points from dice, a pool, or damage already dealt."""

    dice: str | None = None
    bonus: int = 0
    modifier: Literal["none", "ability_modifier"] = "none"
    from_damage: Literal["none", "half_damage_dealt", "all_damage_dealt"] = "none"
    restore_to_maximum: bool = False
    pool: int | None = None


@dataclass(frozen=True)
class TemporaryHitPointsEffect:
    """Grant temporary Hit Points immediately or at a later turn trigger."""

    dice: str | None = None
    value: int = 0
    modifier: Literal["none", "ability_modifier"] = "none"
    trigger: Literal["application", "target_turn_start"] = "application"


@dataclass(frozen=True)
class ArmorClassModifierEffect:
    """Contribute a temporary numeric adjustment to effective Armor Class."""

    value: int
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class RemoveEffect:
    """Remove selected conditions or ongoing-effect categories from a target."""

    removable: tuple[str, ...]
    selection: Literal["one", "all"] = "one"
    conditions: tuple[str, ...] = ()


@dataclass(frozen=True)
class DamageResistanceEffect:
    """Grant resistance to all or one selected damage type for a duration."""

    damage_types: tuple[str, ...]
    selection: Literal["all", "choose_one"] = "all"
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class DamageReductionEffect:
    """Grant a limited dice-based reduction against matching incoming damage."""

    damage_types: tuple[str, ...]
    dice: str
    selection: Literal["all", "choose_one"] = "all"
    limit: int = 1
    period: Literal["turn"] = "turn"
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class SpeedModifierEffect:
    """Add or subtract feet from effective Speed for a duration."""

    feet: int
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class ConditionSaveAdvantageEffect:
    """Grant advantage on saves made to avoid or end named conditions."""

    conditions: tuple[str, ...]
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class DamageImmunityEffect:
    """Grant immunity to the listed damage types for a duration."""

    damage_types: tuple[str, ...]
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class ConditionImmunityEffect:
    """Prevent named conditions and optionally suppress existing applications."""

    conditions: tuple[str, ...]
    suppress_existing: bool = False
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class SenseEffect:
    """Grant a named special sense with a finite range for a duration."""

    sense: Literal["blindsight", "darkvision", "truesight"]
    range_feet: int
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class HitPointMaximumModifierEffect:
    """Adjust maximum Hit Points, optionally changing current Hit Points too."""

    value: int
    also_modify_current: bool = False
    duration: EffectDuration | None = None


@dataclass(frozen=True)
class DestructibleCondition:
    """Define an attackable attachment whose destruction ends a condition."""

    label: str
    armor_class: int
    hit_points: int
    damage_vulnerabilities: tuple[str, ...] = ()
    damage_immunities: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConditionEffect:
    """Apply one condition with provenance, duration, and optional escape rules."""

    condition: str
    duration: EffectDuration | None = None
    requirements: tuple[CapabilityRequirement, ...] = ()
    escape_dc: int | None = None
    source_capacity: int | None = None
    destructible: DestructibleCondition | None = None
    ends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class ForcedMovementEffect:
    """Move a target in a required direction without spending its movement."""

    direction: str
    distance_feet: int
    up_to: bool


@dataclass(frozen=True)
class TeleportEffect:
    """Move a target instantly to a selected destination space."""

    distance_feet: int
    line_of_sight: bool = False


@dataclass(frozen=True)
class SpeedMultiplierEffect:
    """Multiply effective Speed by a rational value for a duration."""

    numerator: int
    denominator: int
    duration: EffectDuration


@dataclass(frozen=True)
class ProhibitReactionsEffect:
    """Prevent a target from taking reactions for a duration."""

    duration: EffectDuration


@dataclass(frozen=True)
class TurnEconomyRestrictionEffect:
    """Force a target to choose between specified turn resources."""

    choose_between: tuple[str, ...]
    duration: EffectDuration


@dataclass(frozen=True)
class CompelledTurnEffect:
    """Offer a closed set of instructions for a target's compelled turn."""

    options: tuple[Literal["approach", "drop", "flee", "grovel", "halt"], ...]
    duration: EffectDuration


@dataclass(frozen=True)
class RollModifierEffect:
    """Contribute a contextual numeric or advantage-state roll adjustment."""

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
    consume_on_use: bool = False


@dataclass(frozen=True)
class ControlEffect:
    """Grant remote control of a target subject to communication and range."""

    communication: str | None
    communication_range_feet: int | Literal["unlimited"] | None
    control_range_feet: int | None
    duration: EffectDuration


@dataclass(frozen=True)
class GainMemoriesEffect:
    """Gain a qualifying target's memories when the configured event occurs."""

    requirement: CreatureTypeRequirement
    trigger: str


CapabilityEffect = (
    DamageEffect
    | HitPointMaximumReductionEffect
    | AttackHitDamageEffect
    | AttackHitRetaliationEffect
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
    | TeleportEffect
    | SpeedMultiplierEffect
    | ProhibitReactionsEffect
    | TurnEconomyRestrictionEffect
    | CompelledTurnEffect
    | RollModifierEffect
    | ControlEffect
    | GainMemoriesEffect
)
