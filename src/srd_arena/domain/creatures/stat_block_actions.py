"""Model declared and executable actions originating in creature stat blocks."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from srd_arena.domain.capabilities import (
    CapabilityEffect,
    CapabilityGrant,
    CapabilityTarget,
    OutcomeStage,
    ResourcePoolDefinition,
)

if TYPE_CHECKING:
    from srd_arena.domain.spells import Spell


@dataclass(frozen=True)
class DeclaredStatBlockAction:
    """Preserve an authored stat-block entry even when it is not executable yet.

    The frontend uses declarations to display unavailable or unimplemented
    actions instead of silently hiding rules text that lacks structured mechanics.
    """

    name: str
    display_name: str
    description: str
    capability_type: str | None = None
    section: Literal["action", "bonus_action"] = "action"


@dataclass(frozen=True)
class AttackActionDefinition:
    """Describe an executable stat-block attack and its hit capability effects."""

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
    """Describe a stat-block action resolved by a fixed Difficulty Class save."""

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
    """Describe a stat-block action whose effects require no attack or save."""

    name: str
    target: CapabilityTarget
    effects: tuple[CapabilityEffect, ...]
    grant: CapabilityGrant | None = None
    resource_pool: ResourcePoolDefinition | None = None


@dataclass(frozen=True)
class SpellOption:
    """Bind one NPC spell choice to its cast level and per-stat-block resources."""

    name: str
    source: str | None = None
    cast_level: int | None = None
    uses: int | Literal["at_will"] | None = None
    resource_pool: ResourcePoolDefinition | None = None
    spell: Spell | None = None
    grant: CapabilityGrant | None = None


@dataclass(frozen=True)
class SpellcastingActionDefinition:
    """Collect the spells available through an NPC stat-block casting action."""

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
