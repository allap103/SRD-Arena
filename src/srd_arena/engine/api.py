"""Stable in-process API for driving SRD Arena engine sessions.

Driving adapters should import commands, observations, and the session from
this module. Implementation modules remain free to change without becoming
accidental frontend dependencies.
"""

from .commands import (
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
from .observations import (
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
from .session import Session

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
    "GameUpdate",
    "GridObservation",
    "InitiativeObservation",
    "InventoryItemObservation",
    "OngoingEffectObservation",
    "PositionObservation",
    "SceneObservation",
    "SelectAction",
    "Session",
    "SetResourceAllocation",
    "SpellSlotObservation",
    "TargetResourceAllocationObservation",
    "TargetResourceLimitObservation",
    "TargetingObservation",
    "TransitionObservation",
]
