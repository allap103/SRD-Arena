from dataclasses import dataclass
from typing import Literal

from ..capabilities import (
    CapabilityEffect,
    OutcomeStage,
    CapabilityTarget,
    CapabilityDefinition,
)

@dataclass(frozen=True)
class DeclaredStatBlockAction:
    name: str
    display_name: str
    description: str
    capability_type: str | None = None
    section: Literal["action", "bonus_action"] = "action"

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
    target: CapabilityTarget
    reach_feet: int | None
    range_normal_feet: int | None
    range_long_feet: int | None
    hit: tuple[CapabilityEffect, ...]
    resource: ActionResource | None = None
    capability: CapabilityDefinition | None = None


@dataclass(frozen=True)
class SavingThrowActionDefinition:
    name: str
    target: CapabilityTarget
    ability: str
    dc: int
    failure: tuple[OutcomeStage, ...]
    success: tuple[CapabilityEffect, ...]
    success_damage: Literal["none", "half"]
    always: tuple[CapabilityEffect, ...]
    resource: ActionResource | None = None
    capability: CapabilityDefinition | None = None


@dataclass(frozen=True)
class AutomaticActionDefinition:
    name: str
    target: CapabilityTarget
    effects: tuple[CapabilityEffect, ...]
    resource: ActionResource | None = None
    capability: CapabilityDefinition | None = None


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
