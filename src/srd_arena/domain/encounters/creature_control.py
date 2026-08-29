"""Coordinate discovery and execution of creature-selected encounter actions.

Detailed movement, spell-selection, and capability behavior lives in the
focused :mod:`actions.creature_actions` package. This module owns their
high-level discovery and execution entry points.
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
from .encounter_models.actions import EncounterAction
from .encounter_models.decisions import DecisionFrame
from .encounter_models.resolution import ActionExecutionResult

if TYPE_CHECKING:
    from .encounter import EncounterState


def execute_creature_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
) -> ActionExecutionResult:
    """Execute one selected action through its focused domain handler.

    Standard actions pass through the shared begin/finish lifecycle even when
    their focused handler performs all rule-specific work.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import patch
    >>> action = EncounterAction("Wait", "wait")
    >>> decision = DecisionFrame("turn", "hero", "turn", "active")
    >>> context = SimpleNamespace(
    ...     actor=SimpleNamespace(creature=object()),
    ...     progress=SimpleNamespace(),
    ...     action_id="action-1",
    ...     rejection=None,
    ... )
    >>> marker = object()
    >>> with patch(
    ...     "srd_arena.domain.encounters.creature_control.begin_action_execution",
    ...     return_value=context,
    ... ), patch(
    ...     "srd_arena.domain.encounters.creature_control.execute_capability_action",
    ...     return_value=False,
    ... ), patch(
    ...     "srd_arena.domain.encounters.creature_control."
    ...     "execute_spell_selection_action",
    ...     return_value=False,
    ... ), patch(
    ...     "srd_arena.domain.encounters.creature_control.execute_standard_action",
    ...     return_value=True,
    ... ), patch(
    ...     "srd_arena.domain.encounters.creature_control.finish_action_execution",
    ...     return_value=marker,
    ... ) as finish:
    ...     result = execute_creature_action(SimpleNamespace(), action, decision)
    >>> (result is marker, finish.call_args.kwargs["action_ends_turn"])
    (True, True)
    """

    context = begin_action_execution(state, action, decision)
    actor = context.actor.creature
    progress = context.progress
    action_id = context.action_id

    if context.rejection is not None:
        return finish_action_execution(context, action_ends_turn=False)

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
    ) or execute_standard_action(
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
