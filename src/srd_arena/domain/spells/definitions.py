from dataclasses import dataclass, field

from ..effects.modifiers import RollModifier

from ..capabilities import CapabilityRequirement
from ..capabilities import CapabilityActivation, CapabilityDefinition


@dataclass(frozen=True)
class SpellRef:
    name: str
    source: str | None = None


@dataclass(frozen=True)
class SpellDamage:
    dice: str
    damage_type: str


@dataclass(frozen=True)
class FollowUpSpellResolution:
    resolution: str
    target: str
    damage: tuple[SpellDamage, ...]
    save_ability: str | None = None
    half_damage_on_save: bool = False
    area_radius_feet: int | None = None
    slot_damage_increment: str | None = None


@dataclass(frozen=True)
class SpellCapability:
    resolution: str
    damage: tuple[SpellDamage, ...]
    save_ability: str | None = None
    attack_mode: str | None = None
    half_damage_on_save: bool = False
    automatic_failure_creature_types: tuple[str, ...] = ()
    disadvantage_creature_types: tuple[str, ...] = ()
    cantrip_damage_by_level: tuple[tuple[int, str], ...] = ()
    slot_damage_increment: str | None = None
    conditions: tuple[str, ...] = ()
    condition_choice: bool = False
    duration_rounds: int | None = None
    concentration: bool = False
    repeat_save_trigger: str | None = None
    expires_on_source_turn_end: bool = False
    repeat_failure_conditions: tuple[str, ...] = ()
    repeat_failure_damage: tuple[SpellDamage, ...] = ()
    end_events: tuple[tuple[str, str], ...] = ()
    damage_repeat_save_advantage: bool = False
    save_advantage_against_opponents: bool = False
    automatic_success_condition_immunities: tuple[str, ...] = ()
    automatic_success_traits: tuple[str, ...] = ()
    self_removal_blocked_conditions: tuple[str, ...] = ()
    follow_up_resolutions: tuple[FollowUpSpellResolution, ...] = ()
    slot_healing_dice_increment: str | None = None
    slot_healing_bonus_increment: int = 0
    slot_temporary_hit_points_increment: int = 0
    slot_maximum_hit_point_increment: int = 0
    roll_modifiers: tuple[RollModifier, ...] = ()
    recast_ends_previous: bool = False
    roll_modifier_ability_choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Spell:
    id: str
    name: str
    source: str | None
    level: int
    school: str | None = None
    casting_time: tuple[dict[str, object], ...] = ()
    range_data: dict[str, object] = field(default_factory=dict)
    duration_data: tuple[dict[str, object], ...] = ()
    components: dict[str, object] = field(default_factory=dict)
    saving_throw_abilities: tuple[str, ...] = ()
    condition_inflict: tuple[str, ...] = ()
    removable_conditions: tuple[str, ...] = ()
    removable_effect_kinds: tuple[str, ...] = ()
    remove_effect_selection: str | None = None
    damage_dice: str | None = None
    damage_inflict: tuple[str, ...] = ()
    area_tags: tuple[str, ...] = ()
    geometry_mode: str = "point_target"
    area_size_feet: int | None = None
    concentration: bool = False
    target_requirements: tuple[CapabilityRequirement, ...] = ()
    definition: CapabilityDefinition | None = None
    capability: SpellCapability | None = None
    activation: CapabilityActivation | None = None
