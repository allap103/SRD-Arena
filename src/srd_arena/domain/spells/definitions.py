from dataclasses import dataclass, field
from typing import Literal

from ..capabilities import (
    CapabilityActivation,
    CapabilityDefinition,
    CapabilityRequirement,
)


@dataclass(frozen=True)
class SpellRef:
    name: str
    source: str | None = None


@dataclass(frozen=True)
class SpellDamage:
    dice: str
    damage_type: str


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
    recast_ends_previous: bool = False
    self_removal_blocked_conditions: tuple[str, ...] = ()
    target_requirements: tuple[CapabilityRequirement, ...] = ()
    definition: CapabilityDefinition | None = None
    activation: CapabilityActivation | None = None
    resolver_id: Literal["slow"] | None = None
