"""Typed read boundary between session execution and application projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from srd_arena.domain.encounters.actions.eligibility_rules.models import (
    ActionEligibility,
)
from srd_arena.domain.encounters.encounter import EncounterState

EXIT_CHOICE_TEXT = "Exit game"
CONTINUE_CHOICE_TEXT = "Continue"


@dataclass(frozen=True)
class SpellOptionDetails:
    """Expose spell-specific selections needed to configure one action option.

    These values describe the engine's current executable choice. They do not
    duplicate the authored spell definition or ask a client to interpret spell
    rules.
    """

    source_id: str | None
    target_ref: str | None
    target_refs: tuple[str, ...]
    aim_point: tuple[float, float] | None
    resource_level: int | None
    selected_condition: str | None
    selected_damage_type: str | None
    selected_ability: str | None
    healing_allocations: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class StatBlockOptionDetails:
    """Identify the stat-block entry and target behind an executable option."""

    source_id: str | None
    target_ref: str | None


@dataclass(frozen=True)
class DirectTargetOptionDetails:
    """Identify the creature affected by a direct-target engine option."""

    target_ref: str | None


@dataclass(frozen=True)
class FeatureOptionDetails:
    """Identify the creature feature selected by an executable option."""

    feature_id: str


@dataclass(frozen=True)
class MovementOptionDetails:
    """Expose the grid direction encoded by a discrete movement option."""

    direction: str


@dataclass(frozen=True)
class ResourceAllocationOptionDetails:
    """Identify a target whose share of a staged resource can be changed."""

    target_ref: str


ActionOptionDetails = (
    SpellOptionDetails
    | StatBlockOptionDetails
    | DirectTargetOptionDetails
    | FeatureOptionDetails
    | MovementOptionDetails
    | ResourceAllocationOptionDetails
)


@dataclass(frozen=True)
class ActionAim:
    """Request that an advertised area action be aimed at a battlefield point."""

    x: float
    y: float


@dataclass(frozen=True)
class ActionResourceAllocation:
    """Request an exact resource amount for one target in a staged action."""

    target_ref: str
    amount: int


ActionConfiguration = ActionAim | ActionResourceAllocation


@dataclass(frozen=True)
class ActionOptionCost:
    """Report the turn resources an advertised action would consume."""

    movement: int = 0
    action: int = 0
    bonus_action: int = 0
    reaction: int = 0


@dataclass(frozen=True)
class ActionOption:
    """One normalized action candidate with its rule-level eligibility facts."""

    id: str
    label: str
    kind: str
    creature_ref: str
    cost: ActionOptionCost = ActionOptionCost()
    source_trigger_id: str | None = None
    preferred_attack_type: str | None = None
    preferred_attack_name: str | None = None
    eligibility: ActionEligibility = field(default_factory=ActionEligibility)
    implemented: bool = True
    details: ActionOptionDetails | None = None

    @property
    def enabled(self) -> bool:
        """Return whether the action is implemented and passes eligibility.

        >>> ActionOption("dodge", "Dodge", "action", "hero").enabled
        True
        >>> from srd_arena.domain.encounters.actions.eligibility_rules.models import EligibilityFailure
        >>> failure = ActionEligibility((EligibilityFailure("stunned", "Actor is stunned"),))
        >>> ActionOption("dodge", "Dodge", "action", "hero", eligibility=failure).enabled
        False
        """
        return self.implemented and self.eligibility.allowed

    @property
    def availability(
        self,
    ) -> Literal["available", "unavailable", "unimplemented"]:
        """Return the action's three-state client presentation status.

        >>> ActionOption("dodge", "Dodge", "action", "hero").availability
        'available'
        >>> ActionOption("future", "Future", "action", "hero", implemented=False).availability
        'unimplemented'
        """
        if not self.implemented:
            return "unimplemented"
        return "available" if self.eligibility.allowed else "unavailable"


@dataclass(frozen=True)
class SessionRead:
    """Deliberate typed inputs used to project one application observation.

    This is an internal application-core query, not a public client DTO. The
    encounter state reference is borrowed for read-only projection and never
    crosses the public application boundary.
    """

    scene_id: str
    scene_text: str | None
    action_options: tuple[ActionOption, ...]
    encounter_state: EncounterState | None
    transition_message: str | None
    team_ids: tuple[str, ...]
    creature_labels: Mapping[str, str]
    creature_team_ids: Mapping[str, str]
    item_names: Mapping[str, str]
    requires_automatic_advance: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "creature_labels",
            MappingProxyType(dict(self.creature_labels)),
        )
        object.__setattr__(
            self,
            "creature_team_ids",
            MappingProxyType(dict(self.creature_team_ids)),
        )
        object.__setattr__(
            self,
            "item_names",
            MappingProxyType(dict(self.item_names)),
        )
