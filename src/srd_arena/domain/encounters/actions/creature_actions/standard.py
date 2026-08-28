"""Execute small encounter-native actions that do not invoke capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...attack_economy import consume_action
from ...encounter_models.actions import EncounterAction
from ...encounter_models.decisions import DecisionFrame
from ...encounter_models.resolution import EncounterProgress
from ...ongoing_effects import resolve_spell_lifecycle_event
from ...state_runtime import create_event

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
            raise ValueError("Wake action requires a creature reference.")
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
                f"{actor.creature.name} wakes "
                f"{state.creatures[action.value].creature.name}.",
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
