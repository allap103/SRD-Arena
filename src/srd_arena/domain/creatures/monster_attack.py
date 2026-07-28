from dataclasses import dataclass, field

from .stat_block_actions import ActionEffect


@dataclass(frozen=True)
class MonsterAttackDamage:
    dice: str
    bonus: int
    damage_type: str


@dataclass(frozen=True)
class MonsterAttack:
    name: str
    attack_modes: tuple[str, ...]
    attack_bonus: int
    damage_dice: str
    damage_bonus: int
    damage_type: str
    range_normal: int | None = None
    range_long: int | None = None
    properties: tuple[str, ...] = field(default_factory=tuple)
    additional_damage: tuple[MonsterAttackDamage, ...] = field(
        default_factory=tuple
    )
    hit_effects: tuple[ActionEffect, ...] = field(default_factory=tuple)
    reach_feet: int | None = None
