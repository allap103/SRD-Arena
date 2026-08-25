"""Action resolution results and attack outcome data."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ...capabilities import CapabilityEffect, DamageEffect
from ...effects.triggered import TriggeredEffect
from ...rolls.dice import CheckResult, DicePoolResult
from .actions import CreatureRef, EncounterAction
from .decisions import DecisionFrame, DecisionRequest
from .state import EncounterCreatureState


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
    PAUSE_FOR_DECISION = "pause_for_decision"
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
class DecisionExecutionResult:
    progress: EncounterProgress
    action_id: str
    completed: bool


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
    sourced_damage_modifier: int = 0
    damage_modifier_label: str = "STR mod"
    attack_type: str = "melee"
    damage_type: str = "damage"
    critical_hit: bool = False
    weapon_id: str | None = None
    weapon_name: str | None = None
    weapon_properties: tuple[str, ...] = ()
    additional_damage: int = 0
    additional_damage_details: tuple[dict[str, object], ...] = ()
    hit_effects: tuple[CapabilityEffect, ...] = ()


@dataclass
class DamageRerollRequest(DecisionRequest):
    """A resolved hit waiting for its optional damage rerolls."""

    action_id: str
    attacker_ref: CreatureRef
    target_ref: CreatureRef
    attacker_label: str
    target_label: str
    attacks_remaining: int
    attack: AttackOutcome
    triggered_effect: TriggeredEffect
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
    hit_effects: tuple[CapabilityEffect, ...] = ()
    reach_feet: int | None = None
