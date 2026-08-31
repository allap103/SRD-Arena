"""Immutable engine read models exposed to game clients."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from .values import EngineValue, freeze_mapping


@dataclass(frozen=True)
class ActionReasonObservation:
    """Machine-readable reason why an advertised action cannot be selected."""

    code: str
    message: str


@dataclass(frozen=True)
class ActionObservation:
    """A stable selectable option advertised at one decision point."""

    id: str
    label: str
    kind: str
    creature_ref: str
    cost: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))
    enabled: bool = True
    availability: Literal["available", "unavailable", "unimplemented"] = "available"
    reasons: tuple[ActionReasonObservation, ...] = ()
    source_trigger_id: str | None = None
    preferred_attack_type: str | None = None
    preferred_attack_name: str | None = None
    source_id: str | None = None
    source_label: str | None = None
    source_level: int | None = None
    resource_level: int | None = None
    feature_id: str | None = None
    movement_direction: str | None = None
    target_ref: str | None = None
    aim_point: tuple[float, float] | None = None
    area_preview: Mapping[str, EngineValue] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cost", freeze_mapping(self.cost))
        if self.area_preview is not None:
            object.__setattr__(
                self,
                "area_preview",
                freeze_mapping(self.area_preview),
            )

    @property
    def unavailable_reason(self) -> str | None:
        """Join all human-readable unavailability reasons for display.

        >>> reason = ActionReasonObservation("stunned", "Actor is stunned")
        >>> ActionObservation("wait", "Wait", "action", "hero", reasons=(reason,)).unavailable_reason
        'Actor is stunned'
        >>> ActionObservation("wait", "Wait", "action", "hero").unavailable_reason is None
        True
        """
        return "\n".join(reason.message for reason in self.reasons) or None

    @property
    def unavailable_reasons(self) -> tuple[str, ...]:
        """Return unavailability messages without presentation formatting.

        >>> reasons = (ActionReasonObservation("a", "First"),
        ...            ActionReasonObservation("b", "Second"))
        >>> ActionObservation("wait", "Wait", "action", "hero", reasons=reasons).unavailable_reasons
        ('First', 'Second')
        """
        return tuple(reason.message for reason in self.reasons)


@dataclass(frozen=True)
class SceneObservation:
    """Current scene text and all actions the client may display."""

    scene_id: str
    scene_text: str | None
    action_details: tuple[ActionObservation, ...]


@dataclass(frozen=True)
class GridObservation:
    """Dimensions of the current encounter grid in cells."""

    width: int
    height: int


@dataclass(frozen=True)
class PositionObservation:
    """One creature's grid-cell position."""

    x: int
    y: int


@dataclass(frozen=True)
class DecisionObservation:
    """Stable identity and actor of the decision awaiting resolution."""

    id: str
    kind: str
    creature_ref: str


@dataclass(frozen=True)
class InitiativeObservation:
    """One creature's place in encounter initiative."""

    creature_ref: str
    total: int


@dataclass(frozen=True)
class SpellSlotObservation:
    """Remaining and maximum spell slots at one slot level."""

    level: int
    remaining: int
    maximum: int


@dataclass(frozen=True)
class FeatureActionObservation:
    """Action granted by a creature feature and its action-economy cost."""

    feature_id: str
    label: str
    economy: str


@dataclass(frozen=True)
class AttributeObservation:
    """Client-visible level, abilities, and proficiency of one creature."""

    level: int
    strength: int
    dexterity: int
    constitution: int
    wisdom: int
    intelligence: int
    charisma: int
    proficiency_bonus: int


@dataclass(frozen=True)
class InventoryItemObservation:
    """Stable identity and display name of one carried item."""

    item_id: str
    name: str


@dataclass(frozen=True)
class CreatureObservation:
    """Frontend-neutral snapshot of one encounter combatant."""

    creature_ref: str
    creature_id: str
    name: str
    label: str
    token_image: str | None
    team_id: str
    position: PositionObservation
    health: int
    max_health: int
    is_alive: bool
    action_available: bool
    bonus_action_available: bool
    reaction_available: bool
    attacks_remaining: int
    attacks_per_attack_action: int
    movement_remaining: int
    movement_total: int
    movement_remaining_feet: int
    movement_total_feet: int
    effective_conditions: tuple[str, ...]
    spell_slots: tuple[SpellSlotObservation, ...]
    feature_actions: tuple[FeatureActionObservation, ...]
    armor_class: int
    attributes: AttributeObservation
    inventory: tuple[InventoryItemObservation, ...]


@dataclass(frozen=True)
class OngoingEffectObservation:
    """Client-visible summary of one ongoing buff, debuff, or other effect."""

    kind: str
    polarity: str
    applied_by_ref: str | None
    definition_id: str
    target_refs: tuple[str, ...]
    label: str


@dataclass(frozen=True)
class TargetResourceLimitObservation:
    """Maximum resource amount assignable to one staged target."""

    target_ref: str
    maximum: int


@dataclass(frozen=True)
class TargetResourceAllocationObservation:
    """Resource amount currently assigned to one staged target."""

    target_ref: str
    amount: int


@dataclass(frozen=True)
class TargetingObservation:
    """Current staged target selection and optional resource allocation."""

    source_id: str
    source_label: str
    selected_target_refs: tuple[str, ...]
    maximum_targets: int
    repeat_target_allocations: bool
    require_full_target_count: bool
    resource_pool_total: int | None
    resource_allocations: tuple[TargetResourceAllocationObservation, ...]
    resource_limits: tuple[TargetResourceLimitObservation, ...]


@dataclass(frozen=True)
class EncounterObservation:
    """Complete client-visible snapshot of the active encounter."""

    encounter_id: str
    grid: GridObservation
    round_number: int
    decision: DecisionObservation
    creatures: tuple[CreatureObservation, ...]
    initiative: tuple[InitiativeObservation, ...]
    ongoing_effects: tuple[OngoingEffectObservation, ...]
    team_ids: tuple[str, ...]
    targeting: TargetingObservation | None

    def creature(self, creature_ref: str) -> CreatureObservation:
        """Return a combatant by its stable encounter reference.

        >>> from unittest.mock import Mock
        >>> hero = Mock(creature_ref="hero")
        >>> encounter = EncounterObservation(
        ...     "demo", GridObservation(5, 5), 1,
        ...     DecisionObservation("turn:1", "turn", "hero"),
        ...     (hero,), (), (), ("heroes",), None,
        ... )
        >>> encounter.creature("hero") is hero
        True
        """

        return next(
            creature
            for creature in self.creatures
            if creature.creature_ref == creature_ref
        )


@dataclass(frozen=True)
class EncounterCompletionObservation:
    """Message presented after the encounter has been completed."""

    message: str


@dataclass(frozen=True)
class GameObservation:
    """Everything a client may inspect about the current decision point."""

    scene: SceneObservation
    encounter: EncounterObservation | None
    completion: EncounterCompletionObservation | None
    requires_automatic_advance: bool
