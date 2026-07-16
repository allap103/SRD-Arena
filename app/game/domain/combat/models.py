from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generator

from ..creature import Creature
from ..item import Item
from ..scene import Behavior, Encounter, Position
from ..status import Status, StatusSnapshot
from ..rules.config import RulesConfig
from ..rules.dice import CheckResult, DicePoolResult
from ..rules.types import RuleGrant

CreatureRef = str


@dataclass
class ActionCost:
    movement: int = 0
    action: int = 0
    bonus_action: int = 0
    reaction: int = 0


@dataclass
class EncounterAction:
    label: str
    kind: str
    value: str | int | None = None
    id: str = ""
    actor_ref: CreatureRef = "player"
    source_trigger_id: str | None = None
    cost: ActionCost = field(default_factory=ActionCost)


@dataclass
class DecisionFrame:
    id: str
    actor_ref: CreatureRef
    kind: str
    reason: str
    parent_frame_id: str | None = None
    parent_action_id: str | None = None
    can_pass: bool = False


@dataclass
class CombatEvent:
    seq: int
    type: str
    actor_ref: CreatureRef | None = None
    frame_id: str | None = None
    action_id: str | None = None
    data: dict[str, object] = field(default_factory=dict)


@dataclass
class EncounterProgress:
    messages: list[tuple[str, str]] = field(default_factory=list)
    transition: str | None = None
    events: list[CombatEvent] = field(default_factory=list)
    paused_for_decision: bool = False
    paused_for_ai: bool = False


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
    player_movement_remaining: int | None = None
    player_actions_remaining: int = 1
    player_magic_actions_remaining: int = 1
    player_attacks_remaining: int = 0
    player_bonus_action_available: bool = True
    player_reaction_available: bool = True

    @property
    def player_action_available(self) -> bool:
        return self.player_actions_remaining > 0


@dataclass
class InterruptState:
    decision_stack: list[DecisionFrame] = field(default_factory=list)
    pending_action: PendingAction | None = None
    pending_attack: PendingAttack | None = None


@dataclass
class BehaviorContext:
    player_position: Position
    enemy_position: Position
    can_attack: bool


@dataclass
class PendingAction:
    id: str
    kind: str
    actor_ref: CreatureRef
    direction: str
    from_position: Position
    to_position: Position
    resume_enemy_index: int | None = None
    remaining_movement_after: int | None = None
    trigger_id: str | None = None


@dataclass
class EncounterEnemyState:
    actor_id: str
    creature: Creature
    position: Position
    behavior: Behavior
    patrol_index: int = 0
    reaction_available: bool = True
    movement_remaining: int | None = None

    @property
    def is_alive(self) -> bool:
        return self.creature.get_health() > 0


@dataclass
class EncounterSnapshotEnemy:
    actor_id: str
    current_health: int
    position: Position
    patrol_index: int = 0
    reaction_available: bool = True
    movement_remaining: int | None = None


@dataclass
class InitiativeEntry:
    actor_ref: CreatureRef
    roll: int
    modifier: int
    total: int


@dataclass
class InitiativeEntrySnapshot:
    actor_ref: CreatureRef
    roll: int
    modifier: int
    total: int


@dataclass
class DecisionFrameSnapshot:
    id: str
    actor_ref: CreatureRef
    kind: str
    reason: str
    parent_frame_id: str | None = None
    parent_action_id: str | None = None
    can_pass: bool = False


@dataclass
class PendingActionSnapshot:
    id: str
    kind: str
    actor_ref: CreatureRef
    direction: str
    from_position: Position
    to_position: Position
    resume_enemy_index: int | None = None
    remaining_movement_after: int | None = None
    trigger_id: str | None = None


@dataclass
class PendingAttackSnapshot:
    action_id: str
    attacker_ref: CreatureRef
    target_ref: CreatureRef
    target_index: int
    attacker_label: str
    target_label: str
    attacks_remaining: int
    attack_roll: int
    attack_roll_detail: dict[str, object]
    damage_dice: str
    damage_die_rolls: list[list[int]]
    damage_die_sides: list[int]
    damage_modifier: int
    damage_modifier_label: str
    attack_type: str
    damage_type: str
    critical_hit: bool
    weapon_id: str | None
    weapon_name: str | None
    continuation: str
    reaction: bool
    rule_id: str
    rule_source_type: str
    rule_source_id: str
    rule_trigger: str
    rule_operation: str
    rule_conditions: dict[str, object]
    rule_parameters: dict[str, object]


@dataclass
class EncounterSnapshot:
    scene_id: str
    player_position: Position
    control_mode: str = "default"
    turn_index: int = 0
    round_number: int = 1
    player_movement_remaining: int | None = None
    player_actions_remaining: int = 1
    player_magic_actions_remaining: int = 1
    player_action_available: bool = True
    player_attacks_remaining: int = 0
    player_bonus_action_available: bool = True
    player_reaction_available: bool = True
    action_sequence: int = 1
    frame_sequence: int = 1
    event_sequence: int = 1
    initiative_order: list[CreatureRef] = field(default_factory=lambda: ["player"])
    initiative_entries: list[InitiativeEntrySnapshot] = field(default_factory=list)
    decision_stack: list[DecisionFrameSnapshot] = field(default_factory=list)
    pending_action: PendingActionSnapshot | None = None
    pending_attack: PendingAttackSnapshot | None = None
    conditions: list[StatusSnapshot] = field(default_factory=list)
    enemies: list[EncounterSnapshotEnemy] = field(default_factory=list)


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


@dataclass
class PendingAttack:
    action_id: str
    attacker_ref: CreatureRef
    target_ref: CreatureRef
    target_index: int
    attacker_label: str
    target_label: str
    attacks_remaining: int
    attack: AttackOutcome
    rule: RuleGrant
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


@dataclass
class EncounterStateData:
    scene_id: str
    definition: Encounter
    player_position: Position
    enemies: list[EncounterEnemyState]
    control_mode: str = "default"
    ai_action_limit: int | None = None
    round: RoundState = field(default_factory=RoundState)
    turn: TurnState = field(default_factory=TurnState)
    interrupts: InterruptState = field(default_factory=InterruptState)
    action_sequence: int = 1
    frame_sequence: int = 1
    event_sequence: int = 1
    initiative_order: list[CreatureRef] = field(default_factory=lambda: ["player"])
    initiative_entries: list[InitiativeEntry] = field(default_factory=list)
    conditions: list[Status] = field(default_factory=list)
    item_templates: dict[str, Item] = field(default_factory=dict)
    rules_config: RulesConfig = field(default_factory=RulesConfig)
    _behaviors: list[Generator[EncounterAction | None, BehaviorContext, None]] = field(
        default_factory=list,
        repr=False,
    )
