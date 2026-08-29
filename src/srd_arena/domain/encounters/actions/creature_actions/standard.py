"""Execute small encounter-native actions that do not invoke capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...attack_economy import consume_action
from ...behaviors import is_adjacent
from ...encounter_models.actions import EncounterAction
from ...encounter_models.decisions import DecisionFrame
from ...encounter_models.resolution import EncounterProgress
from ...ongoing_effects import resolve_spell_lifecycle_event
from ...state_runtime import create_event
from ..rejections import reject_action

if TYPE_CHECKING:
    from ...encounter import EncounterState


def execute_standard_action(
    state: EncounterState,
    action: EncounterAction,
    decision: DecisionFrame,
    progress: EncounterProgress,
    action_id: str,
) -> bool:
    """Execute wake/wait actions and report whether this handler recognized one.

    >>> from types import SimpleNamespace
    >>> actor = SimpleNamespace(creature=SimpleNamespace(name="Hero"))
    >>> state = SimpleNamespace(
    ...     creatures={"hero": actor}, event_sequence=1,
    ... )
    >>> progress = EncounterProgress()
    >>> execute_standard_action(
    ...     state, EncounterAction("Wait", "wait"),
    ...     DecisionFrame("turn", "hero", "turn", "active"),
    ...     progress, "wait-1"
    ... )
    True
    >>> (progress.messages[-1], progress.events[-1].data["kind"])
    (('system', 'Hero waits.'), 'wait')
    """

    actor = state.creatures[decision.creature_ref]
    if action.kind == "wake_spell_target":
        if not isinstance(action.value, str):
            reject_action(
                state,
                progress,
                actor_ref=decision.creature_ref,
                action_id=action_id,
                action_kind=action.kind,
                message="Wake action requires a creature reference.",
                reason_code="target_required",
            )
            return True
        target = state.creatures.get(action.value)
        if target is None or not target.is_alive:
            reject_action(
                state,
                progress,
                actor_ref=decision.creature_ref,
                action_id=action_id,
                action_kind=action.kind,
                message="The target is no longer available.",
                reason_code="target_unavailable",
                details={"target_ref": action.value},
            )
            return True
        if not is_adjacent(actor.position, target.position):
            reject_action(
                state,
                progress,
                actor_ref=decision.creature_ref,
                action_id=action_id,
                action_kind=action.kind,
                message="The target is no longer within reach.",
                reason_code="target_out_of_range",
                details={"target_ref": action.value},
            )
            return True
        if not _can_wake_spell_target(state, action.value):
            reject_action(
                state,
                progress,
                actor_ref=decision.creature_ref,
                action_id=action_id,
                action_kind=action.kind,
                message="That magical sleep effect is no longer active.",
                reason_code="wake_unavailable",
                details={"target_ref": action.value},
            )
            return True
        consume_action(state, allow_magic=False)
        resolve_spell_lifecycle_event(
            state,
            "adjacent_creature_wakes_target",
            actor_ref=decision.creature_ref,
            target_ref=action.value,
            progress=progress,
        )
        progress.messages.append(
            (
                "system",
                f"{actor.creature.name} wakes {target.creature.name}.",
            )
        )
        progress.events.append(
            create_event(
                state,
                "action_resolved",
                creature_ref=decision.creature_ref,
                action_id=action_id,
                data={"kind": "wake_spell_target", "target_ref": action.value},
            )
        )
    elif action.kind == "wait":
        progress.messages.append(("system", f"{actor.creature.name} waits."))
        progress.events.append(
            create_event(
                state,
                "action_resolved",
                creature_ref=decision.creature_ref,
                action_id=action_id,
                data={"kind": "wait"},
            )
        )
    else:
        return False
    return True


def _can_wake_spell_target(state: EncounterState, target_ref: str) -> bool:
    """Return whether an active effect lets an adjacent creature wake a target."""

    return any(
        target_ref in effect.target_refs
        and any(
            configured.event == "adjacent_creature_wakes_target"
            for configured in effect.lifecycle.end_events
        )
        for effect in state.ongoing_effects
    )
