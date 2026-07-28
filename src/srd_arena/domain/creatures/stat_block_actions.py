from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ActionTarget:
    kind: Literal["self", "creature", "area"]
    range_feet: int | None = None
    shape: str | None = None
    size_feet: int | None = None
    width_feet: int | None = None
    line_of_sight: bool = False
    requirements: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class ActionEffect:
    kind: str
    parameters: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionOutcomeStage:
    effects: tuple[ActionEffect, ...]
    repeat_saves: tuple[dict[str, object], ...] = ()


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
    resource: dict[str, object] | None = None


StatBlockActionDefinition = (
    AttackActionDefinition | SavingThrowActionDefinition
)
