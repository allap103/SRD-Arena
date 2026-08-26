"""Public read models exposed to game clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping


@dataclass(frozen=True)
class ActionReasonObservation:
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
    area_preview: dict[str, object] | None = None

    @property
    def unavailable_reason(self) -> str | None:
        return "\n".join(reason.message for reason in self.reasons) or None

    @property
    def unavailable_reasons(self) -> tuple[str, ...]:
        return tuple(reason.message for reason in self.reasons)


@dataclass(frozen=True)
class SceneObservation:
    scene_id: str
    scene_text: str | None
    action_details: tuple[ActionObservation, ...]


@dataclass(frozen=True)
class GridObservation:
    width: int
    height: int


@dataclass(frozen=True)
class PositionObservation:
    x: int
    y: int


@dataclass(frozen=True)
class DecisionObservation:
    id: str
    kind: str
    creature_ref: str


@dataclass(frozen=True)
class InitiativeObservation:
    creature_ref: str
    total: int


@dataclass(frozen=True)
class SpellSlotObservation:
    level: int
    remaining: int
    maximum: int


@dataclass(frozen=True)
class FeatureActionObservation:
    feature_id: str
    label: str
    economy: str


@dataclass(frozen=True)
class AttributeObservation:
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
    item_id: str
    name: str


@dataclass(frozen=True)
class CreatureObservation:
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
    kind: str
    polarity: str
    applied_by_ref: str | None
    definition_id: str
    target_refs: tuple[str, ...]
    label: str


@dataclass(frozen=True)
class TargetResourceLimitObservation:
    target_ref: str
    maximum: int


@dataclass(frozen=True)
class TargetResourceAllocationObservation:
    target_ref: str
    amount: int


@dataclass(frozen=True)
class TargetingObservation:
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
        """Return a combatant by its stable encounter reference."""

        return next(
            creature
            for creature in self.creatures
            if creature.creature_ref == creature_ref
        )


@dataclass(frozen=True)
class TransitionObservation:
    message: str


@dataclass(frozen=True)
class GameObservation:
    """Everything a client may inspect about the current decision point."""

    scene: SceneObservation
    encounter: EncounterObservation | None
    transition: TransitionObservation | None
    requires_automatic_advance: bool
