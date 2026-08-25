"""Dispatch executable attack, feature, grapple, item, and stat-block actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...models import EncounterAction, EncounterProgress
from ..grappling import resolve_escape_action
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
    """Execute a recognized non-spell capability and report whether it matched."""

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
        state._resolve_feature_action(
            actor,
            action.value,
            progress,
            action_id,
        )
    elif action.kind == "grapple":
        state._resolve_grapple_action(
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
        state._resolve_utilize_action(
            actor,
            action.value,
            progress,
            action_id,
        )
    else:
        return False
    return True

