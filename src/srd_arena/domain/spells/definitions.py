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
    damage_dice: str | None = None
    damage_inflict: tuple[str, ...] = ()
    area_tags: tuple[str, ...] = ()
    geometry_mode: str = "point_target"
    area_size_feet: int | None = None
    concentration: bool = False
    target_requirements: tuple[ActionRequirement, ...] = ()
    mechanics: ImmediateSpellMechanics | None = None
