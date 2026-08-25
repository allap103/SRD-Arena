"""Coordinate discovery and execution of creature-selected encounter actions.

Detailed movement, spell-selection, and capability behavior lives in the
focused :mod:`actions.creature_actions` package.  This module remains the
stable surface bound onto :class:`EncounterState`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .actions.creature_actions.capability_execution import (
    execute_capability_action,
)
from .actions.creature_actions.discovery import (
    _stat_block_display_name,
    available_creature_actions,
    creature_action_candidates,
)
from .actions.creature_actions.lifecycle import (
    begin_action_execution,
    finish_action_execution,
)
from .actions.creature_actions.movement import execute_movement
from .actions.creature_actions.spell_invocation import execute_spell_invocation
from .actions.creature_actions.spell_selection import (
    execute_spell_selection_action,
)
from .actions.creature_actions.standard import execute_standard_action
from .models import ActionExecutionResult, DecisionFrame, EncounterAction

if TYPE_CHECKING:
    from .encounter import EncounterState


def execute_creature_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> ActionExecutionResult:
    """Execute one selected action through its focused domain handler."""

    context = begin_action_execution(state, action, decision)
    actor = context.actor.creature
    progress = context.progress
    action_id = context.action_id

    if action.kind == "move":
        movement_result = execute_movement(state, action, decision, context)
        if movement_result is not None:
            return movement_result
    elif execute_capability_action(
        state,
        actor,
        action,
        progress,
        action_id,
    ):
        pass
    elif action.kind == "spell":
        execute_spell_invocation(
            state,
            actor,
            action,
            decision,
            progress,
            action_id,
        )
    elif execute_spell_selection_action(
        state,
        actor,
        action,
        progress,
        action_id,
    ):
        pass
    elif execute_standard_action(
        state,
        action,
        decision,
        progress,
        action_id,
    ):
        pass
    else:
        raise ValueError(f"Unsupported creature action: {action.kind}")

    return finish_action_execution(
        context,
        action_ends_turn=action.kind == "wait",
    )


__all__ = [
    "_stat_block_display_name",
    "available_creature_actions",
    "begin_action_execution",
    "creature_action_candidates",
    "execute_creature_action",
    "finish_action_execution",
]
