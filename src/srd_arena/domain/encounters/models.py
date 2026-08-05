from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from ..creatures import Creature
from ..equipment import Item
from ..geometry import MovementBudget, MovementCost, Position
from .definitions import EncounterBehavior, EncounterDefinition
from ..effects.conditions import AppliedCondition
from ..effects.runtime import CreatureRelationship, OngoingEffect
from ..geometry import GeometryConfig
from ..rolls.dice import CheckResult, DicePoolResult
from ..effects.triggered import TriggeredEffect
from ..creatures.stat_block_actions import ActionEffect, DamageEffect
from ..creatures.multiattack import MultiattackStep

CreatureRef = str

if TYPE_CHECKING:
    from .action_selection import ActionSelector


@dataclass
class ActionCost:
    movement: MovementCost = MovementCost(0)
    action: int = 0
    bonus_action: int = 0
    reaction: int = 0

    def __post_init__(self) -> None:
        self.movement = MovementCost(self.movement)


@dataclass
class EncounterAction:
    label: str
    kind: str
    value: str | int | tuple[float, float] | None = None
    id: str = ""
    creature_ref: CreatureRef | None = None
    source_trigger_id: str | None = None
    preferred_attack_type: str | None = None
    preferred_attack_name: str | None = None
    cost: ActionCost = field(default_factory=ActionCost)


@dataclass
class DecisionFrame:
    id: str
    creature_ref: CreatureRef
    kind: str
    reason: str
    parent_frame_id: str | None = None
    parent_action_id: str | None = None
    can_pass: bool = False


@dataclass
class CombatEvent:
    seq: int
    type: str
    creature_ref: CreatureRef | None = None
    frame_id: str | None = None
    action_id: str | None = None
    data: dict[str, object] = field(default_factory=dict)


@dataclass
class EncounterProgress:
    messages: list[tuple[str, str]] = field(default_factory=list)
    transition: str | None = None
    events: list[CombatEvent] = field(default_factory=list)
    paused_for_decision: bool = False
    paused_for_pacing: bool = False


class ActionExecutionOutcome(str, Enum):
    CONTINUE_TURN = "continue_turn"
    END_TURN = "end_turn"
    PAUSE_FOR_REACTION = "pause_for_reaction"
    ENCOUNTER_COMPLETE = "encounter_complete"


@dataclass
class ActionExecutionContext:
    actor_ref: CreatureRef
    actor: EncounterCreatureState
    decision: DecisionFrame
    action: EncounterAction
    action_id: str
    progress: EncounterProgress = field(default_factory=EncounterProgress)


@dataclass
class ActionExecutionResult:
    context: ActionExecutionContext
    outcome: ActionExecutionOutcome

    @property
    def progress(self) -> EncounterProgress:
        return self.context.progress


@dataclass
class RoundState:
    number: int = 1

    def advance(self) -> None:
        self.number += 1

    def matches(self, round_number: int | None) -> bool:
        return round_number == self.number


@dataclass
class TurnState:
    index: int = 0


@dataclass
class PendingSpellCast:
    action: EncounterAction
    spell_id: str
    selected_target_refs: list[CreatureRef]
    maximum_targets: int


@dataclass
class InterruptState:
    decision_stack: list[DecisionFrame] = field(default_factory=list)
    pending_action: PendingAction | None = None
    pending_attack: PendingAttack | None = None
    pending_spell_cast: PendingSpellCast | None = None


@dataclass
class BehaviorContext:
    target_position: Position
    actor_position: Position
    can_attack: bool


@dataclass
class PendingAction:
    id: str
    kind: str
    creature_ref: CreatureRef
    direction: str
    from_position: Position
    to_position: Position
    remaining_movement_after: MovementBudget | None = None
    trigger_id: str | None = None


@dataclass
class EncounterCreatureState:
    creature_id: str
    creature: Creature
    position: Position
    behavior: EncounterBehavior
    patrol_index: int = 0
    reaction_available: bool = True
    movement_remaining: MovementBudget | None = None
    actions_remaining: int = 1
    magic_actions_remaining: int = 1
    attacks_remaining: int = 0
    pending_multiattack: list[MultiattackStep] = field(default_factory=list)
    bonus_action_available: bool = True

    @property
    def is_alive(self) -> bool:
        return self.creature.get_health() > 0


@dataclass
class InitiativeEntry:
    creature_ref: CreatureRef
    roll: int
    modifier: int
    total: int


@dataclass
class AttackOutcome:
    messages: list[tuple[str, str]]
    hit: bool
    attack_roll: int
    damage: int
    defender_defeated: bool
    attack_roll_detail: dict[str, object]
    damage_roll_detail: dict[str, object] | None = None
    attack_check: CheckResult | None = None
    damage_roll: DicePoolResult | None = None
    damage_dice: str | None = None
    damage_modifier: int = 0
    damage_modifier_label: str = "STR mod"
    attack_type: str = "melee"
    damage_type: str = "damage"
    critical_hit: bool = False
    weapon_id: str | None = None
    weapon_name: str | None = None
    weapon_properties: tuple[str, ...] = ()
    additional_damage: int = 0
    additional_damage_details: tuple[dict[str, object], ...] = ()
    hit_effects: tuple[ActionEffect, ...] = ()


@dataclass
class PendingAttack:
    action_id: str
    attacker_ref: CreatureRef
    target_ref: CreatureRef
    attacker_label: str
    target_label: str
    attacks_remaining: int
    attack: AttackOutcome
    triggered_effect: TriggeredEffect
    continuation: str = "return_to_turn"
    reaction: bool = False


@dataclass(frozen=True)
class AttackSource:
    name: str
    damage_dice: str
    damage_bonus: int
    damage_bonus_label: str
    damage_type: str
    attack_bonus: int
    attack_bonus_label: str
    attack_modes: tuple[str, ...]
    ability_modifier: int = 0
    proficiency_bonus: int = 0
    range_normal: int | None = None
    range_long: int | None = None
    weapon_id: str | None = None
    weapon_name: str | None = None
    weapon_properties: tuple[str, ...] = ()
    additional_damage: tuple[DamageEffect, ...] = ()
    hit_effects: tuple[ActionEffect, ...] = ()
    reach_feet: int | None = None


@dataclass
class EncounterStateData:
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
