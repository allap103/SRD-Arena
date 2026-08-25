"""Compatibility facade for encounter action, decision, resolution, and state models."""

from .encounter_models.actions import ActionCost, CreatureRef, EncounterAction
from .encounter_models.decisions import (
    CloseParentDecision,
    DecisionContinuation,
    DecisionFrame,
    DecisionRequest,
    InterruptState,
    OpportunityAttackRequest,
    PendingMovement,
    PendingSpellCast,
    ResumeMovement,
)
from .encounter_models.resolution import (
    ActionExecutionContext,
    ActionExecutionOutcome,
    ActionExecutionResult,
    AttackOutcome,
    AttackSource,
    CombatEvent,
    DamageRerollRequest,
    DecisionExecutionResult,
    EncounterProgress,
)
from .encounter_models.state import (
    BehaviorContext,
    EncounterCreatureState,
    EncounterStateData,
    InitiativeEntry,
    RoundState,
    TurnState,
)

__all__ = [
    "ActionCost",
    "ActionExecutionContext",
    "ActionExecutionOutcome",
    "ActionExecutionResult",
    "AttackOutcome",
    "AttackSource",
    "BehaviorContext",
    "CloseParentDecision",
    "CombatEvent",
    "CreatureRef",
    "DamageRerollRequest",
    "DecisionContinuation",
    "DecisionExecutionResult",
    "DecisionFrame",
    "DecisionRequest",
    "EncounterAction",
    "EncounterCreatureState",
    "EncounterProgress",
    "EncounterStateData",
    "InitiativeEntry",
    "InterruptState",
    "OpportunityAttackRequest",
    "PendingMovement",
    "PendingSpellCast",
    "ResumeMovement",
    "RoundState",
    "TurnState",
]
