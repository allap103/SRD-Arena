"""Expose the public encounters package API."""

from .definitions import (
    EncounterBehavior,
    EncounterDefinition,
    EncounterParticipant,
    EncounterTeam,
)
from .encounter import EncounterState
from .encounter_models.actions import EncounterAction
from .orchestration import EncounterOrchestrator
from .terrain import CoverDegree, TerrainCell, TerrainMovementMode, TerrainTraversal

__all__ = [
    "CoverDegree",
    "EncounterAction",
    "EncounterBehavior",
    "EncounterDefinition",
    "EncounterOrchestrator",
    "EncounterParticipant",
    "EncounterState",
    "EncounterTeam",
    "TerrainCell",
    "TerrainMovementMode",
    "TerrainTraversal",
]
