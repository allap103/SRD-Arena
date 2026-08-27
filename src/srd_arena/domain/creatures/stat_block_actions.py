"""Provide stat block actions support for the creatures package."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from ..capabilities import (
    CapabilityEffect,
    CapabilityGrant,
    CapabilityTarget,
    OutcomeStage,
    ResourcePoolDefinition,
)

if TYPE_CHECKING:
    from ..spells import Spell


@dataclass(frozen=True)
class DeclaredStatBlockAction:
    """Represent a declared stat block action."""

    name: str
    display_name: str
    description: str
    capability_type: str | None = None
    section: Literal["action", "bonus_action"] = "action"


@dataclass(frozen=True)
class AttackActionDefinition:
    """Represent an attack action definition."""

    name: str
    attack_modes: tuple[str, ...]
    attack_bonus: int
    target: CapabilityTarget
    reach_feet: int | None
    range_normal_feet: int | None
    range_long_feet: int | None
    hit: tuple[CapabilityEffect, ...]
    grant: CapabilityGrant | None = None
    resource_pool: ResourcePoolDefinition | None = None


@dataclass(frozen=True)
class SavingThrowActionDefinition:
    """Represent a saving throw action definition."""

    name: str
    target: CapabilityTarget
    ability: str
    dc: int
    failure: tuple[OutcomeStage, ...]
    success: tuple[CapabilityEffect, ...]
    success_damage: Literal["none", "half"]
    always: tuple[CapabilityEffect, ...]
    grant: CapabilityGrant | None = None
    resource_pool: ResourcePoolDefinition | None = None


@dataclass(frozen=True)
class AutomaticActionDefinition:
    """Represent an automatic action definition."""

    name: str
    target: CapabilityTarget
    effects: tuple[CapabilityEffect, ...]
    grant: CapabilityGrant | None = None
    resource_pool: ResourcePoolDefinition | None = None


@dataclass(frozen=True)
class SpellOption:
    """Represent a spell option."""

    name: str
    source: str | None = None
    cast_level: int | None = None
    uses: int | Literal["at_will"] | None = None
    resource_pool: ResourcePoolDefinition | None = None
    spell: Spell | None = None
    grant: CapabilityGrant | None = None


@dataclass(frozen=True)
class SpellcastingActionDefinition:
    """Represent a spellcasting action definition."""

    name: str
    ability: str
    spells: tuple[SpellOption, ...]
    resource_pool: ResourcePoolDefinition | None = None


StatBlockActionDefinition = (
    AttackActionDefinition
    | SavingThrowActionDefinition
    | AutomaticActionDefinition
    | SpellcastingActionDefinition
)
