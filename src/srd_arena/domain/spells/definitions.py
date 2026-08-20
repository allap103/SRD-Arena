from dataclasses import dataclass, field

from ..creatures.stat_block_actions import ActionRequirement


@dataclass(frozen=True)
class SpellRef:
    name: str
    source: str | None = None


@dataclass(frozen=True)
class SpellDamage:
    dice: str
    damage_type: str


@dataclass(frozen=True)
class SpellHealing:
    dice: str | None = None
    bonus: int = 0
    add_spellcasting_modifier: bool = False
    restore_to_maximum: bool = False
    pool: int | None = None


@dataclass(frozen=True)
class SpellTemporaryHitPoints:
    dice: str | None = None
    value: int = 0
    add_spellcasting_modifier: bool = False


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
class ImmediateSpellMechanics:
    resolution: str
    target: str
    damage: tuple[SpellDamage, ...]
    save_ability: str | None = None
    attack_mode: str | None = None
    half_damage_on_save: bool = False
    area_shape: str | None = None
    area_radius_feet: int | None = None
    area_length_feet: int | None = None
    area_width_feet: int | None = None
    area_height_feet: int | None = None
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
    target_disposition: str = "enemy"
    repeat_failure_conditions: tuple[str, ...] = ()
    repeat_failure_damage: tuple[SpellDamage, ...] = ()
    end_events: tuple[tuple[str, str], ...] = ()
    damage_repeat_save_advantage: bool = False
    save_advantage_against_opponents: bool = False
    automatic_success_condition_immunities: tuple[str, ...] = ()
    automatic_success_traits: tuple[str, ...] = ()
    self_removal_blocked_conditions: tuple[str, ...] = ()
    base_target_count: int = 1
    slot_target_increment: int = 0
    choose_area_targets: bool = False
    repeat_target_allocations: bool = False
    require_full_target_count: bool = False
    target_count_by_caster_level: tuple[tuple[int, int], ...] = ()
    follow_up_resolutions: tuple[FollowUpSpellResolution, ...] = ()
    healing: tuple[SpellHealing, ...] = ()
    temporary_hit_points: tuple[SpellTemporaryHitPoints, ...] = ()
    slot_healing_dice_increment: str | None = None
    slot_healing_bonus_increment: int = 0
    slot_temporary_hit_points_increment: int = 0
    maximum_hit_point_modifier: int = 0
    also_modify_current_hit_points: bool = False
    slot_maximum_hit_point_increment: int = 0
    damage_resistances: tuple[str, ...] = ()
    damage_resistance_choice: bool = False
    condition_save_advantages: tuple[str, ...] = ()

    @property
    def healing_pool(self) -> int | None:
        return next(
            (healing.pool for healing in self.healing if healing.pool is not None),
            None,
        )


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
    target_requirements: tuple[ActionRequirement, ...] = ()
    mechanics: ImmediateSpellMechanics | None = None
