from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SpellRef:
    name: str
    source: str | None = None


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


@dataclass
class Spellcasting:
    ability: str
    ability_modifier: int
    save_dc: int
    attack_bonus: int
    caster_progression: str
    preparation_mode: str = "fixed"
    cantrips_known: int = 0
    spell_count: int | None = None
    spell_slots_max: dict[int, int] = field(default_factory=dict)
    spell_slots_remaining: dict[int, int] = field(default_factory=dict)
    learned_spells: list[Spell] = field(default_factory=list)
