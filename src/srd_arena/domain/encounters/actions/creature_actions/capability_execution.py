"""Dispatch executable attack, feature, grapple, item, and stat-block actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...encounter_models.actions import EncounterAction
from ...encounter_models.resolution import EncounterProgress
from ..execution import resolve_grapple_action
from ..features import resolve_feature_action
from ..grappling import resolve_escape_action
from ..items import resolve_utilize_action
from ..stat_block import resolve_attack_action, resolve_multiattack_action

if TYPE_CHECKING:
    from ....creatures import Creature
    from ...encounter import EncounterState


def execute_capability_action(
    state: EncounterState,
    actor: Creature,
    action: EncounterAction,
    progress: EncounterProgress,
    action_id: str,
) -> bool:
    """Execute a recognized non-spell capability and report whether it matched.

    >>> from types import SimpleNamespace
    >>> from unittest.mock import Mock, patch
    >>> state = SimpleNamespace()
    >>> progress = EncounterProgress()
    >>> with patch(
    ...     "srd_arena.domain.encounters.actions.creature_actions."
    ...     "capability_execution.resolve_feature_action"
    ... ) as resolve:
    ...     matched = execute_capability_action(
    ...         state, SimpleNamespace(),
    ...         EncounterAction("Surge", "feature", "surge"),
    ...         progress, "feature-1"
    ...     )
    >>> matched
    True
    >>> resolve.call_args.args[2]
    'surge'
    >>> execute_capability_action(
    ...     state, SimpleNamespace(), EncounterAction("Wait", "wait"),
    ...     progress, "wait-1"
    ... )
    False
    """

    if action.kind == "multiattack":
        resolve_multiattack_action(
            state,
            actor,
            action,
            progress,
            action_id,
        )
    elif action.kind == "attack":
        resolve_attack_action(
            state,
            actor,
            action,
            progress,
            action_id,
        )
    elif action.kind == "stat_block":
        from ..stat_block import resolve_stat_block_action

        resolve_stat_block_action(
            state,
            actor,
            action,
            progress,
            action_id,
        )
    elif action.kind == "feature":
        if not isinstance(action.value, str):
            raise ValueError("Feature action requires a feature id.")
        resolve_feature_action(
            state,
            actor,
            action.value,
            progress,
            action_id,
        )
    elif action.kind == "grapple":
        resolve_grapple_action(
            state,
            actor,
            action,
            progress,
            action_id,
        )
    elif action.kind == "escape_grapple":
        resolve_escape_action(
            state,
            actor,
            action,
            progress,
            action_id,
        )
    elif action.kind == "utilize":
        if not isinstance(action.value, str):
            raise ValueError("Utilize action requires an item id.")
        resolve_utilize_action(
            state,
            actor,
            action.value,
            progress,
            action_id,
        )
    else:
        return False
    return True
