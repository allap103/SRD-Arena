"""Round, turn, combatant, and aggregate encounter state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...creatures import Creature
from ...creatures.multiattack import MultiattackStep
from ...effects.conditions import AppliedCondition
from ...effects.runtime import CreatureRelationship, OngoingEffect
from ...equipment import Item
from ...geometry import GeometryConfig, MovementBudget, MovementCost, Position
from ..definitions import EncounterBehavior, EncounterDefinition
from .actions import CreatureRef
from .decisions import InterruptState

if TYPE_CHECKING:
    from ..action_selection import ActionSelector


@dataclass
class RoundState:
    """Represent a round state."""

    number: int = 1

    def advance(self) -> None:
        """Advance the mutable round counter by one.

        >>> round_state = RoundState()
        >>> round_state.advance()
        >>> round_state.number
        2
        """
        self.number += 1

    def matches(self, round_number: int | None) -> bool:
        """Return whether a possibly absent round number is current.

        >>> RoundState(number=3).matches(3)
        True
        >>> RoundState(number=3).matches(None)
        False
        """
        return round_number == self.number


@dataclass
class TurnState:
    """Represent a turn state."""

    index: int = 0


@dataclass
class BehaviorContext:
    """Represent a behavior context."""

    target_position: Position
    actor_position: Position
    can_attack: bool


@dataclass
class EncounterCreatureState:
    """Represent an encounter creature state."""

    creature_id: str
    creature: Creature
    position: Position
    behavior: EncounterBehavior
    patrol_index: int = 0
    reaction_available: bool = True
    movement_remaining: MovementBudget | None = None
    movement_spent_this_turn: MovementCost = field(
        default_factory=lambda: MovementCost(0)
    )
    actions_remaining: int = 1
    action_used_this_turn: bool = False
    magic_actions_remaining: int = 1
    attacks_remaining: int = 0
    attack_action_base_attacks: int = 0
    attack_action_attacks_used: int = 0
    pending_multiattack: list[MultiattackStep] = field(default_factory=list)
    bonus_action_available: bool = True
    bonus_action_used_this_turn: bool = False

    @property
    def is_alive(self) -> bool:
        return self.creature.get_health() > 0


@dataclass
class InitiativeEntry:
    """Represent an initiative entry."""

    creature_ref: CreatureRef
    roll: int
    modifier: int
    total: int


@dataclass
class EncounterStateData:
    """Represent an encounter state data."""

    encounter_id: str
    definition: EncounterDefinition
    creatures: dict[CreatureRef, EncounterCreatureState]
    automatic_action_limit: int | None = None
    round: RoundState = field(default_factory=RoundState)
    turn: TurnState = field(default_factory=TurnState)
    interrupts: InterruptState = field(default_factory=InterruptState)
    action_sequence: int = 1
    frame_sequence: int = 1
    event_sequence: int = 1
    runtime_state_sequence: int = 1
    initiative_order: list[CreatureRef] = field(default_factory=list)
    initiative_entries: list[InitiativeEntry] = field(default_factory=list)
    conditions: list[AppliedCondition] = field(default_factory=list)
    ongoing_effects: list[OngoingEffect] = field(default_factory=list)
    relationships: list[CreatureRelationship] = field(default_factory=list)
    item_templates: dict[str, Item] = field(default_factory=dict)
    geometry_config: GeometryConfig = field(default_factory=GeometryConfig)
    _action_selectors: dict[CreatureRef, ActionSelector] = field(
        default_factory=dict,
        repr=False,
    )
