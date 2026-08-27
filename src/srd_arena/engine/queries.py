"""Typed read boundary between session execution and application projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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
    source_id: str | None
    target_ref: str | None


@dataclass(frozen=True)
class DirectTargetOptionDetails:
    target_ref: str | None


@dataclass(frozen=True)
class FeatureOptionDetails:
    feature_id: str


@dataclass(frozen=True)
class MovementOptionDetails:
    direction: str


@dataclass(frozen=True)
class ResourceAllocationOptionDetails:
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
    x: float
    y: float


@dataclass(frozen=True)
class ActionResourceAllocation:
    target_ref: str
    amount: int


ActionConfiguration = ActionAim | ActionResourceAllocation


@dataclass(frozen=True)
class ActionOptionCost:
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
    eligibility: ActionEligibility = ActionEligibility()
    implemented: bool = True
    details: ActionOptionDetails | None = None

    @property
    def enabled(self) -> bool:
        return self.implemented and self.eligibility.allowed

    @property
    def availability(
        self,
    ) -> Literal["available", "unavailable", "unimplemented"]:
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
