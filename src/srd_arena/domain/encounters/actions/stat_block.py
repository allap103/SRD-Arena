"""Stable facade for authored stat-block action runtime behavior.

The implementation is grouped by responsibility in neighboring
``stat_block_*`` modules. Encounter action dispatch and eligibility import this
facade so those internal boundaries can evolve without spreading imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...creatures import Creature
from ...creatures.stat_block_actions import (
    AutomaticActionDefinition,
    SavingThrowActionDefinition,
)
from .stat_block_attacks import resolve_attack_action
from .stat_block_automatic import resolve_automatic_stat_block_action
from .stat_block_multiattack import (
    executable_multiattack_sequence,
    executable_multiattack_slot_plans,
    resolve_multiattack_action,
)
from .stat_block_resources import (
    consume_stat_block_action_resource,
    recharge_stat_block_actions,
    stat_block_action_resource_available,
)
from .stat_block_saving_throws import resolve_saving_throw_stat_block_action
from .stat_block_validation import stat_block_action_runtime_issue
from ..models import EncounterAction, EncounterProgress

if TYPE_CHECKING:
    from ..encounter import EncounterState

__all__ = [
    "consume_stat_block_action_resource",
    "executable_multiattack_sequence",
    "executable_multiattack_slot_plans",
    "recharge_stat_block_actions",
    "resolve_attack_action",
    "resolve_multiattack_action",
    "resolve_stat_block_action",
    "stat_block_action_resource_available",
    "stat_block_action_runtime_issue",
]


def resolve_stat_block_action(
    state: EncounterState,
    creature: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> None:
    """Dispatch a supported authored action to its focused resolver."""
    definition = creature.stat_block_actions.get(action.preferred_attack_name or "")
    if isinstance(definition, AutomaticActionDefinition):
        resolve_automatic_stat_block_action(
            state,
            creature,
            definition,
            action,
            progress,
            action_id,
        )
        return
    if isinstance(definition, SavingThrowActionDefinition):
        resolve_saving_throw_stat_block_action(
            state,
            creature,
            definition,
            action,
            progress,
            action_id,
        )
        return
    raise ValueError("Executable stat-block action definition required.")
