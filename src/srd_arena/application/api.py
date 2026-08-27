"""Stable in-process API for driving SRD Arena games.

Driving adapters should import application commands, observations, and use
cases from this module. The implementation modules remain free to change
without becoming accidental frontend dependencies.
"""

from srd_arena.application.commands import (
    AimAction,
    CancelTargeting,
    ChangeTarget,
    CommandFailure,
    CommandResult,
    ConfirmTargeting,
    GameCommand,
    GameEvent,
    GameUpdate,
    SelectAction,
    SetResourceAllocation,
)
from srd_arena.application.game import RunningGame
from srd_arena.application.observations import (
    ActionObservation,
    ActionReasonObservation,
    AttributeObservation,
    CreatureObservation,
    DecisionObservation,
    EncounterObservation,
    FeatureActionObservation,
    GameObservation,
    GridObservation,
    InitiativeObservation,
    InventoryItemObservation,
    OngoingEffectObservation,
    PositionObservation,
    SceneObservation,
    SpellSlotObservation,
    TargetingObservation,
    TargetResourceAllocationObservation,
    TargetResourceLimitObservation,
    TransitionObservation,
)
from srd_arena.application.scenarios import ScenarioPresentation, ScenarioSummary
from srd_arena.application.startup import GameStartup

__all__ = [
    "ActionObservation",
    "ActionReasonObservation",
    "AimAction",
    "AttributeObservation",
    "CancelTargeting",
    "ChangeTarget",
    "CommandFailure",
    "CommandResult",
    "ConfirmTargeting",
    "CreatureObservation",
    "DecisionObservation",
    "EncounterObservation",
    "FeatureActionObservation",
    "GameCommand",
    "GameEvent",
    "GameObservation",
    "GameStartup",
    "GameUpdate",
    "GridObservation",
    "InitiativeObservation",
    "InventoryItemObservation",
    "OngoingEffectObservation",
    "PositionObservation",
    "RunningGame",
    "ScenarioPresentation",
    "ScenarioSummary",
    "SceneObservation",
    "SelectAction",
    "SetResourceAllocation",
    "SpellSlotObservation",
    "TargetResourceAllocationObservation",
    "TargetResourceLimitObservation",
    "TargetingObservation",
    "TransitionObservation",
]
