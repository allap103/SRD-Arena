"""Round, turn, combatant, and aggregate encounter state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from srd_arena.domain.creatures import Creature
from srd_arena.domain.creatures.multiattack import MultiattackStep
from srd_arena.domain.effects.conditions import AppliedCondition
from srd_arena.domain.effects.runtime import CreatureRelationship, OngoingEffect
from srd_arena.domain.equipment import Item
from srd_arena.domain.geometry import (
    GeometryConfig,
    MovementBudget,
    MovementCost,
    Position,
)
from srd_arena.domain.rolls.randomness import DiceRoller

from ..definitions import EncounterBehavior, EncounterDefinition
from .actions import CreatureRef
from .decisions import InterruptState

if TYPE_CHECKING:
    from ..action_selection import ActionSelector


@dataclass
class RoundState:
    """Track the encounter's mutable one-based round number."""

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
    """Track the current position within initiative order."""

    index: int = 0


@dataclass
class BehaviorContext:
    """Supply a scripted controller with positions and immediate attack access."""

    target_position: Position
    actor_position: Position
    can_attack: bool


@dataclass
class EncounterCreatureState:
    """Wrap a creature with encounter-specific position and turn resources.

    Controller and team ownership are derived from the encounter definition.
    Intrinsic statistics, health, equipment, and features stay on ``creature``.
    """

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
        """Return whether the encounter creature still has hit points.

        >>> from srd_arena.domain.creatures import Attributes, Equipment, Inventory
        >>> creature = Creature("hero", "Hero", "", Inventory(),
        ...     Attributes(10, 1, 10, 10, 10, 10, 10, 10, 10), Equipment())
        >>> state = EncounterCreatureState("hero", creature, Position(0, 0), EncounterBehavior("hold"))
        >>> state.is_alive
        True
        >>> creature.take_damage(10)
        10
        >>> state.is_alive
        False
        """
        return self.creature.get_health() > 0


@dataclass
class InitiativeEntry:
    """Retain one creature's initiative roll, modifier, and resolved total."""

    creature_ref: CreatureRef
    roll: int
    modifier: int
    total: int


@dataclass
class EncounterStateData:
    """Store all mutable aggregate state for one encounter instance.

    The data includes combatants, clocks, nested decisions, sourced effects,
    relationships, runtime sequences, and action selectors. ``EncounterState``
    constructs this aggregate and exposes its small engine-facing API.
    """

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
    dice: DiceRoller = field(default_factory=DiceRoller, repr=False)
    _action_selectors: dict[CreatureRef, ActionSelector] = field(
        default_factory=dict,
        repr=False,
    )
