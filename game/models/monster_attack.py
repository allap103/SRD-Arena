from dataclasses import dataclass, field


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
